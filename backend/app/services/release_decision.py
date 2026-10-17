"""One bounded definition of the current effective release decision."""
from sqlalchemy import exists, select
from sqlalchemy.orm import aliased

from app.models.approval import ReleaseDecision


def effective_release_decision_statement(release_id):
    successor = aliased(ReleaseDecision)
    return (
        select(ReleaseDecision)
        .where(
            ReleaseDecision.release_id == release_id,
            ~exists(select(1).where(successor.supersedes_id == ReleaseDecision.id)),
        )
        .order_by(ReleaseDecision.decided_at.desc(), ReleaseDecision.id.desc())
        .limit(1)
    )


def effective_release_decision(db, release_id):
    return db.scalars(effective_release_decision_statement(release_id)).first()
