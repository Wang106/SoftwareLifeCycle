"""Bounded read-only aggregation of ASR component differences against a baseline SSR.

For one standard release (the baseline SSR), this projects a bounded aggregate of
every derived application release (ASR) that declares it as its
``standard_base_release_id``. It observes only stored component associations; it
never infers approval, inheritance, readiness or a formal release from counts or
version strings.

Two axes are aggregated:

* ``delta_type`` differences — each ASR component declaration is bucketed by its
  declared ``delta_type`` (UNCHANGED/MODIFIED/ADDED/REMOVED), and further split by
  its ``base_link_status`` (VALID/INVALID/NOT_RECORDED). A declaration whose link is
  not VALID is reported as ``link_status``, never silently treated as a clean
  difference.

* unlinked-base blocks — each baseline SSR component that some derived ASR fails to
  declare (a valid link to) is a "block". The aggregate counts, per baseline
  component definition, how many of the derived ASRs leave it unlinked. A baseline
  component referenced by every ASR is not a block.
"""
import uuid

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.core import (
    ApplicationReleaseDetail,
    ComponentDefinition,
    Release,
    ReleaseComponent,
)

DELTA_TYPES = ("UNCHANGED", "MODIFIED", "ADDED", "REMOVED")
LINK_STATUSES = ("VALID", "INVALID", "NOT_RECORDED")


def _derived_asr_ids(db: Session, base_id: uuid.UUID) -> list[uuid.UUID]:
    rows = db.scalars(
        select(ApplicationReleaseDetail.release_id)
        .join(Release, Release.id == ApplicationReleaseDetail.release_id)
        .where(
            ApplicationReleaseDetail.standard_base_release_id == base_id,
            Release.release_type == "APPLICATION",
        )
        .order_by(ApplicationReleaseDetail.release_id)
    ).all()
    return list(rows)


def _delta_aggregate(db: Session, base_id: uuid.UUID, asr_ids: list[uuid.UUID]) -> dict:
    # A declaration's link is VALID only when its base_component_id points at a
    # baseline component of the same component_definition_id; otherwise INVALID if a
    # base pointer exists, or NOT_RECORDED when absent. This mirrors asr_components.
    b = ReleaseComponent.__table__
    c = ReleaseComponent.__table__.alias("c")
    base_def = select(c.c.component_definition_id).where(c.c.id == b.c.base_component_id).scalar_subquery()
    link_status = case(
        (b.c.base_component_id.is_(None), "NOT_RECORDED"),
        (base_def == b.c.component_definition_id, "VALID"),
        else_="INVALID",
    ).label("link_status")

    buckets = {dt: {ls: 0 for ls in LINK_STATUSES} for dt in DELTA_TYPES}
    if not asr_ids:
        return {"asr_declaration_count": 0, "by_delta_type": buckets}

    rows = db.execute(
        select(b.c.delta_type, link_status, func.count())
        .where(b.c.release_id.in_(asr_ids))
        .group_by(b.c.delta_type, link_status)
    ).all()
    total = 0
    for delta_type, status, count in rows:
        if delta_type in buckets and status in buckets[delta_type]:
            buckets[delta_type][status] = count
            total += count
    return {"asr_declaration_count": total, "by_delta_type": buckets}


def _unlinked_aggregate(db: Session, base_id: uuid.UUID, asr_ids: list[uuid.UUID]) -> dict:
    # Baseline component definitions, in stable order, with the count of derived
    # ASRs that do not carry a valid link to any baseline component of that
    # definition. A definition with zero baseline components is skipped.
    base_components = db.execute(
        select(ReleaseComponent.id, ReleaseComponent.component_definition_id)
        .where(ReleaseComponent.release_id == base_id)
        .order_by(ReleaseComponent.id)
    ).all()

    definitions: dict[uuid.UUID, ComponentDefinition] = {}
    if base_components:
        def_ids = {row.component_definition_id for row in base_components}
        definitions = {
            d.id: d for d in db.scalars(select(ComponentDefinition).where(
                ComponentDefinition.id.in_(def_ids))).all()
        }

    blocks: list[dict] = []
    total_blocks = 0
    for component in base_components:
        if not asr_ids:
            unlinked_count = 0
        else:
            # Count derived ASRs that have a VALID link to this exact baseline
            # component; unlinked = derived_count - valid_linked_count. This keeps
            # the query bounded regardless of how many declarations each ASR has.
            valid_link_exists = select(ReleaseComponent.id).where(
                ReleaseComponent.release_id.in_(asr_ids),
                ReleaseComponent.base_component_id == component.id,
                ReleaseComponent.component_definition_id == component.component_definition_id,
            ).exists()
            # ASRs lacking any such valid link.
            linked_asr_ids = db.scalars(
                select(ReleaseComponent.release_id).where(
                    ReleaseComponent.release_id.in_(asr_ids),
                    ReleaseComponent.base_component_id == component.id,
                    ReleaseComponent.component_definition_id == component.component_definition_id,
                ).distinct()
            ).all()
            unlinked_count = len(asr_ids) - len(set(linked_asr_ids))
        definition = definitions.get(component.component_definition_id)
        blocks.append({
            "baseline_component_id": str(component.id),
            "component_code": definition.code if definition else None,
            "component_name": definition.name if definition else None,
            "unlinked_application_count": unlinked_count,
        })
        if unlinked_count:
            total_blocks += 1
    return {"baseline_component_count": len(base_components), "blocked_component_count": total_blocks,
            "blocks": blocks}


def ssr_asr_aggregated_differences(db: Session, base_id: uuid.UUID) -> dict:
    """Aggregate component differences and blocks for one baseline SSR.

    ``base_id`` identifies a STANDARD ``Release``; the release row is loaded here so
    the projection stays a single bounded read independent of any caller-held ORM
    instance. Read-only, no side effects.
    """
    base_release = db.get(Release, base_id)
    if base_release is None or base_release.release_type != "STANDARD":
        raise ValueError("standard release not found")
    asr_ids = _derived_asr_ids(db, base_release.id)
    delta = _delta_aggregate(db, base_release.id, asr_ids)
    unlinked = _unlinked_aggregate(db, base_release.id, asr_ids)
    return {
        "release": {
            "id": str(base_release.id),
            "version": base_release.version,
            "release_type": base_release.release_type,
            "record_status": base_release.status,
        },
        "derived_application_count": len(asr_ids),
        "delta_type_aggregate": delta,
        "unlinked_base_aggregate": unlinked,
    }
