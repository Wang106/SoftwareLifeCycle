"""Bounded scalar history relationships; withdrawal never resurrects predecessors."""
from sqlalchemy import and_, select
from app.models.acceptance import AcceptanceDvpLink


def successor_id():
    original = AcceptanceDvpLink.__table__
    successor = original.alias('acceptance_successor')
    return select(successor.c.id).where(successor.c.supersedes_id == original.c.id).correlate(original).scalar_subquery()


def effective():
    return and_(AcceptanceDvpLink.action != 'WITHDRAW', successor_id().is_(None))
