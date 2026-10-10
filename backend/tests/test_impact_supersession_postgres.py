"""Migrated PostgreSQL only: locks, retry, append triggers and guarded downgrade."""
import uuid
from types import SimpleNamespace

import pytest
from alembic import command as migration
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from test_command_concurrency_postgres import pg, overlapping_commands
from test_evidence_audit_postgres import evidence_context, command_input
from app.api.issue_views import SnapshotSelection, evidence_summary
from app.models.audit import AuditEvent
from app.models.impact import IssueImpactAssessment
from app.core.config import settings
from app.services.audit import AuditEventService
from app.services.impact_assessment import AssessmentError, record_assessment


def root(engine, ids):
    body = command_input('impact', ids)
    with Session(engine) as db:
        record_assessment(db, 'ISSUE-ORIGINAL', body); db.commit()
    return body


def corrected(ids, original, **changes):
    body = command_input('impact', ids).model_copy(update={
        'supersedes_id': original.request_id, 'correction_reason': 'Reconciled bench result',
        'decision': 'NOT_AFFECTED', **changes})
    return body


def command(body):
    def execute(db):
        try:
            row, _ = record_assessment(db, 'ISSUE-ORIGINAL', body); db.commit()
            return row
        except AssessmentError as exc:
            db.rollback(); return SimpleNamespace(id='conflict:' + str(exc))
    return execute


@pytest.mark.parametrize('pattern', ['same_request', 'competing', 'changed_reason'])
def test_corrections_serialize_on_issue_and_identical_retries_append_once(evidence_context, monkeypatch, pattern):
    engine, ids = evidence_context; original = root(engine, ids)
    first = corrected(ids, original)
    second = first if pattern == 'same_request' else corrected(ids, original) if pattern == 'competing' else first.model_copy(update={'correction_reason': 'Different reason'})
    one, two = overlapping_commands(engine, monkeypatch, command(first), command(second))
    assert one[1] == first.request_id
    assert two[1] == first.request_id if pattern == 'same_request' else str(two[1]).startswith('conflict:')
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(IssueImpactAssessment)) == 2
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == 'ISSUE_IMPACT')) == 2
        assert evidence_summary('ISSUE-ORIGINAL', ids['release'], SnapshotSelection(snapshot_id=ids['snapshot']), db)['assessment']['id'] == str(first.request_id)


def test_audit_interruption_leaves_original_effective_and_lock_reusable(evidence_context, monkeypatch):
    engine, ids = evidence_context; original = root(engine, ids); body = corrected(ids, original)
    record = AuditEventService.record
    def interrupt(self, **kwargs):
        record(self, **kwargs); raise RuntimeError('interrupted after audit flush')
    with Session(engine) as db:
        with monkeypatch.context() as patch:
            patch.setattr(AuditEventService, 'record', interrupt)
            with pytest.raises(RuntimeError):
                try: record_assessment(db, 'ISSUE-ORIGINAL', body); db.commit()
                except Exception: db.rollback(); raise
        assert db.get(IssueImpactAssessment, body.request_id) is None
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.event_no == f'EVT-IMPACT-{body.request_id}')) is None
        assert evidence_summary('ISSUE-ORIGINAL', ids['release'], SnapshotSelection(), db)['assessment']['id'] == str(original.request_id)
    with Session(engine) as db:
        row, created = record_assessment(db, 'ISSUE-ORIGINAL', body); db.commit()
        assert created and row.id == body.request_id


def test_migration_preserves_legacy_rows_and_refuses_loss_of_correction_history(evidence_context):
    engine, ids = evidence_context; original = root(engine, ids); config = Config('alembic.ini')
    migration.downgrade(config, '0020_global_role_status')
    with engine.connect() as db:
        assert db.scalar(text('SELECT decision FROM issue_impact_assessments WHERE id=:id'), {'id': original.request_id}) == original.decision
    migration.upgrade(config, 'head')
    with Session(engine) as db:
        legacy = db.get(IssueImpactAssessment, original.request_id)
        assert legacy.supersedes_id is legacy.correction_reason is None
        body = corrected(ids, original); record_assessment(db, 'ISSUE-ORIGINAL', body); db.commit()
    with pytest.raises(DBAPIError, match='Cannot downgrade while impact corrections exist'):
        migration.downgrade(config, '0020_global_role_status')
    with engine.connect() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version')) == settings.required_db_revision
        assert db.scalar(text('SELECT count(*) FROM issue_impact_assessments')) == 2
        for query in ['UPDATE issue_impact_assessments SET reason=reason WHERE id=:id', 'DELETE FROM issue_impact_assessments WHERE id=:id']:
            with pytest.raises(DBAPIError, match='append-only'):
                db.execute(text(query), {'id': original.request_id})
            db.rollback()


@pytest.mark.parametrize('invalid', ['duplicate_child', 'self', 'missing', 'foreign_context', 'reason_only', 'predecessor_only', 'blank_reason'])
def test_schema_guards_predecessor_uniqueness_context_and_correction_pair(evidence_context, invalid):
    engine, ids = evidence_context; original = root(engine, ids); body = corrected(ids, original)
    with Session(engine) as db:
        if invalid == 'duplicate_child': record_assessment(db, 'ISSUE-ORIGINAL', body); db.commit()
        identifier = uuid.uuid4(); predecessor = original.request_id; reason = 'Correction'
        if invalid == 'self': predecessor = identifier
        if invalid == 'missing': predecessor = uuid.uuid4()
        if invalid == 'reason_only': predecessor = None
        if invalid == 'predecessor_only': reason = None
        if invalid == 'blank_reason': reason = '  '
        # A real but differently numbered frozen snapshot is a foreign context.
        snapshot = ids['snapshot']
        if invalid == 'foreign_context':
            from app.models.snapshot import ReleaseSnapshot
            row = ReleaseSnapshot(release_id=ids['release'], snapshot_no='OTHER', snapshot_number=2, status='FROZEN', content_hash='b' * 64)
            db.add(row); db.commit(); snapshot = row.id
        db.add(IssueImpactAssessment(id=identifier, issue_id=ids['issue'], release_id=ids['release'], snapshot_id=snapshot,
            decision='NOT_AFFECTED', reason='New judgment', actor_name='Reviewer', supersedes_id=predecessor, correction_reason=reason))
        with pytest.raises(IntegrityError): db.commit()
        db.rollback()
        assert db.get(IssueImpactAssessment, identifier) is None
