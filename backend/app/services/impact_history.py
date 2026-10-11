"""One SQL-bounded context terminal, including withdrawals and legacy leaves."""
from sqlalchemy import case, func, select
from sqlalchemy.orm import aliased
from app.models.impact import IssueImpactAssessment


def action_value(row):
    return row.action or ('SUPERSEDE' if row.supersedes_id else 'ASSESS')


def action_expression(row=IssueImpactAssessment):
    return func.coalesce(row.action, case((row.supersedes_id.is_not(None), 'SUPERSEDE'), else_='ASSESS'))


def successor_id():
    original = IssueImpactAssessment.__table__
    successor = original.alias('impact_successor')
    return select(successor.c.id).where(successor.c.supersedes_id == original.c.id).correlate(original).scalar_subquery()


def effective():
    # Leaves include WITHDRAW. Filtering it before selecting the terminal resurrects old roots.
    return successor_id().is_(None)


def terminal_order(row=IssueImpactAssessment):
    return (row.context_seq.desc().nullslast(), row.created_at.desc(), row.id.desc())


def terminal_id(issue_id, release_id, snapshot_id, *correlations):
    j = aliased(IssueImpactAssessment)
    child = aliased(IssueImpactAssessment)
    has_child = select(child.id).where(child.supersedes_id == j.id).correlate(j).exists()
    stmt = select(j.id).where(j.issue_id == issue_id, j.release_id == release_id,
        j.snapshot_id == snapshot_id, ~has_child).order_by(*terminal_order(j)).limit(1)
    if correlations:
        stmt = stmt.correlate(*correlations)
    return stmt.scalar_subquery()


def current_event(db, issue_id, release_id, snapshot_id):
    j = IssueImpactAssessment
    return db.scalar(select(j).where(j.id == terminal_id(issue_id, release_id, snapshot_id)))


def next_sequence(db, issue_id, release_id, snapshot_id):
    # Caller holds the existing Issue FOR UPDATE through commit/rollback.
    j = IssueImpactAssessment
    return (db.scalar(select(j.context_seq).where(j.issue_id == issue_id, j.release_id == release_id,
        j.snapshot_id == snapshot_id, j.context_seq.is_not(None)).order_by(j.context_seq.desc()).limit(1)) or 0) + 1


def observation(row):
    return {'context_state': 'UNASSESSED' if row is None else 'WITHDRAWN' if action_value(row) == 'WITHDRAW' else 'JUDGED',
        'terminal_event_id': str(row.id) if row else None,
        'terminal_action': action_value(row) if row else None}
