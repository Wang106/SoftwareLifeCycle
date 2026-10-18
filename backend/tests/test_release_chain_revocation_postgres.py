"""Migrated PostgreSQL locks, immutability, guards and downgrade safety."""
import uuid

import pytest
from alembic import command as migration
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from test_distribution_concurrency_postgres import chain
from test_command_concurrency_postgres import pg, count, overlapping_commands
from app.models.audit import AuditEvent
from app.models.revocation import ReleaseChainRevocation
from app.services.revocation import RevocationService


@pytest.mark.parametrize("same_key", [False, True])
def test_competing_release_revocations_are_serialized(chain, monkeypatch, same_key):
    engine, contexts = chain
    release_id = contexts[0]["release"]
    key = uuid.uuid4()
    other = key if same_key else uuid.uuid4()
    first, second = overlapping_commands(
        engine, monkeypatch,
        lambda db: RevocationService(db).revoke("RELEASE", release_id, "Safety issue", request_id=key),
        lambda db: RevocationService(db).revoke("RELEASE", release_id, "Safety issue", request_id=other),
    )
    assert first[0] == "ok"
    assert second[0] == ("ok" if same_key else "conflict")
    if same_key:
        assert first[1] == second[1]
    with Session(engine) as db:
        assert count(db, ReleaseChainRevocation) == 1
        assert count(db, AuditEvent, event_type="RELEASE_CHAIN_REVOCATION") == 1


def test_append_only_old_writer_guard_and_guarded_downgrade(chain):
    engine, contexts = chain
    context = contexts[0]
    with Session(engine, expire_on_commit=False) as db:
        row = RevocationService(db).revoke(
            "RELEASE", context["release"], "Permanent safety withdrawal", request_id=uuid.uuid4()
        )
        for sql in (
            "UPDATE release_chain_revocations SET reason=reason WHERE id=:id",
            "DELETE FROM release_chain_revocations WHERE id=:id",
        ):
            with pytest.raises(DBAPIError, match="append-only"):
                db.execute(text(sql), {"id": row.id}); db.commit()
            db.rollback()
        with pytest.raises(DBAPIError, match="new permission-bearing records are forbidden"):
            db.execute(text("""INSERT INTO delivery_packages
                (id, package_no, revision, release_id, snapshot_id, recipient_type,
                 recipient_code, purpose, status, created_at)
                SELECT :id, 'OLD-WRITER', 1, release_id, snapshot_id,
                       recipient_type, recipient_code, purpose, 'READY', now()
                  FROM delivery_packages WHERE id=:package"""),
                {"id": uuid.uuid4(), "package": context["package"]})
            db.commit()
        db.rollback()
    with pytest.raises(DBAPIError, match="revocation history would be lost"):
        migration.downgrade(Config("alembic.ini"), "0025_release_decision_supersession")
