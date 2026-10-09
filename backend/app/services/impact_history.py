"""SQL-bounded predecessor links and effective leaves; never a timestamp resurrection."""
from sqlalchemy import select
from app.models.impact import IssueImpactAssessment


def successor_id():
    original = IssueImpactAssessment.__table__
    successor = original.alias('impact_successor')
    return select(successor.c.id).where(successor.c.supersedes_id == original.c.id).correlate(original).scalar_subquery()


def effective():
    return successor_id().is_(None)
