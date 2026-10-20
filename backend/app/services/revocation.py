from dataclasses import dataclass
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.actor import ActorContext
from app.models.approval import ReleaseDecision
from app.models.core import Release
from app.models.distribution import DeliveryPackage, Distribution, SoftwareAuthorization
from app.models.revocation import ReleaseChainRevocation
from app.services.audit import commit_with_audit
from app.services.command_retry import atomic_command, retry_result
from app.services.release_decision import effective_release_decision


class RevocationError(ValueError):
    pass


class RevocationReviewContext(BaseModel):
    """Versioned, exact reviewed identities; legacy requests omit this entirely."""
    model_config = ConfigDict(extra="forbid")
    version: Literal[1]
    release_id: uuid.UUID
    snapshot_id: uuid.UUID
    release_decision_id: uuid.UUID
    delivery_package_id: uuid.UUID | None
    distribution_id: uuid.UUID | None
    authorization_id: uuid.UUID | None

    @field_validator("version", mode="before")
    @classmethod
    def exact_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("version must be integer 1")
        return value

    @field_validator("release_id", "snapshot_id", "release_decision_id",
                     "delivery_package_id", "distribution_id", "authorization_id", mode="before")
    @classmethod
    def canonical_uuid(cls, value):
        if value is not None and not isinstance(value, uuid.UUID):
            if not isinstance(value, str) or str(uuid.UUID(value)) != value:
                raise ValueError("context UUIDs must use canonical lowercase form")
        return value


@dataclass(frozen=True)
class ChainContext:
    release: Release
    package: DeliveryPackage | None
    distribution: Distribution | None
    authorization: SoftwareAuthorization | None


def _review_context(chain, kind, target_id, decision):
    if decision is None or decision.decision != "RELEASE":
        return None
    nodes = [chain.release, chain.package, chain.distribution, chain.authorization]
    depth = ["RELEASE", "DELIVERY_PACKAGE", "DISTRIBUTION", "AUTHORIZATION"].index(kind)
    if any(node is None for node in nodes[:depth + 1]) or nodes[depth].id != target_id:
        return None
    if ((chain.package and chain.package.release_id != chain.release.id)
            or (chain.distribution and chain.distribution.delivery_package_id != chain.package.id)
            or (chain.authorization and (chain.authorization.distribution_id != chain.distribution.id
                                        or chain.authorization.release_id != chain.release.id))):
        return None
    return {"version": 1, "release_id": str(chain.release.id),
            "snapshot_id": str(decision.snapshot_id), "release_decision_id": str(decision.id),
            "delivery_package_id": str(chain.package.id) if chain.package else None,
            "distribution_id": str(chain.distribution.id) if chain.distribution else None,
            "authorization_id": str(chain.authorization.id) if chain.authorization else None}


def _chain(db: Session, kind: str, target_id, *, lock: bool = False) -> ChainContext:
    authorization = db.get(SoftwareAuthorization, target_id) if kind == "AUTHORIZATION" else None
    distribution_id = authorization.distribution_id if authorization else (target_id if kind == "DISTRIBUTION" else None)
    distribution = db.get(Distribution, distribution_id) if distribution_id else None
    package_id = (distribution.delivery_package_id if distribution else
                  target_id if kind == "DELIVERY_PACKAGE" else None)
    package = db.get(DeliveryPackage, package_id) if package_id else None
    release_id = (authorization.release_id if authorization else package.release_id if package else
                  target_id if kind == "RELEASE" else None)
    release = db.get(Release, release_id) if release_id else None
    if release is None or (kind == "DELIVERY_PACKAGE" and package is None) or (
        kind == "DISTRIBUTION" and distribution is None) or (
        kind == "AUTHORIZATION" and authorization is None):
        raise RevocationError("Revocation target not found")
    if authorization and package and authorization.release_id != package.release_id:
        raise RevocationError("Authorization release does not match its distribution chain")
    if lock:
        def locked(model, row_id):
            return db.scalar(select(model).where(model.id == row_id).with_for_update()
                             .execution_options(populate_existing=True)) if row_id else None
        release = locked(Release, release.id)
        package = locked(DeliveryPackage, package.id if package else None)
        distribution = locked(Distribution, distribution.id if distribution else None)
        authorization = locked(SoftwareAuthorization, authorization.id if authorization else None)
    return ChainContext(release, package, distribution, authorization)


def governance_state(db: Session, kind: str, target_id, *, include_review: bool = False) -> dict:
    chain = _chain(db, kind, target_id)
    target_column = {
        "RELEASE": ReleaseChainRevocation.release_id,
        "DELIVERY_PACKAGE": ReleaseChainRevocation.delivery_package_id,
        "DISTRIBUTION": ReleaseChainRevocation.distribution_id,
        "AUTHORIZATION": ReleaseChainRevocation.authorization_id,
    }[kind]
    target_path = [
        ("RELEASE", chain.release.id),
        ("DELIVERY_PACKAGE", chain.package.id if chain.package else None),
        ("DISTRIBUTION", chain.distribution.id if chain.distribution else None),
        ("AUTHORIZATION", chain.authorization.id if chain.authorization else None),
    ]
    predicates = []
    for ancestor_kind, value in target_path:
        if value is None:
            continue
        column = {
            "RELEASE": ReleaseChainRevocation.release_id,
            "DELIVERY_PACKAGE": ReleaseChainRevocation.delivery_package_id,
            "DISTRIBUTION": ReleaseChainRevocation.distribution_id,
            "AUTHORIZATION": ReleaseChainRevocation.authorization_id,
        }[ancestor_kind]
        predicates.append(column == value)
    rows = db.scalars(select(ReleaseChainRevocation).where(or_(*predicates))
        .order_by(ReleaseChainRevocation.revoked_at, ReleaseChainRevocation.id)).all()
    own = next((row for row in rows if getattr(row, target_column.key) == target_id), None)
    ancestors = [row for row in rows if row is not own]
    state = "REVOKED" if own else "BLOCKED_BY_ANCESTOR" if ancestors else "ACTIVE"
    return {
        "target_kind": kind,
        "target_id": str(target_id),
        **({"review_context": _review_context(chain, kind, target_id,
            effective_release_decision(db, chain.release.id)) if state == "ACTIVE" else None}
            if include_review else {}),
        "recorded_status": getattr(chain.authorization or chain.distribution or chain.package or chain.release, "status", None),
        "governance_state": state,
        "eligible_for_new_work": state == "ACTIVE",
        "self_revocation": _read(own),
        "ancestor_revocations": [_read(row) for row in ancestors],
    }


def ensure_chain_active(db: Session, kind: str, target_id, error_type=ValueError):
    state = governance_state(db, kind, target_id)
    if not state["eligible_for_new_work"]:
        raise error_type(f"{kind.lower()} is {state['governance_state'].lower()} and cannot authorize new work")


def lock_chain(db: Session, kind: str, target_id, error_type=RevocationError):
    """Acquire existing chain rows in the shared root-to-leaf order."""
    try:
        return _chain(db, kind, target_id, lock=True)
    except RevocationError as exc:
        raise error_type(str(exc)) from exc


def _read(row):
    if row is None:
        return None
    return {"id": str(row.id), "revocation_no": row.revocation_no,
            "target_kind": row.target_kind, "reason": row.reason,
            "revoked_by": row.revoked_by, "revoked_at": row.revoked_at}


class RevocationService:
    def __init__(self, db: Session):
        self.db = db

    def revoke(self, kind: str, target_id, reason: str, actor_context=None, request_id=None,
               expected_context: RevocationReviewContext | None = None):
        with atomic_command(self.db, RevocationError):
            return self._revoke(kind, target_id, reason, actor_context, request_id, expected_context)

    def _revoke(self, kind, target_id, reason, actor_context, request_id, expected_context):
        if kind not in {"RELEASE", "DELIVERY_PACKAGE", "DISTRIBUTION", "AUTHORIZATION"}:
            raise RevocationError("Unsupported revocation target")
        reason = reason.strip()
        if not reason or len(reason) > 4000:
            raise RevocationError("reason must contain 1 to 4000 characters")
        actor = actor_context or ActorContext.legacy(None)
        # Resolve first, then lock the complete existing chain in canonical order.
        context = _chain(self.db, kind, target_id)
        context = _chain(self.db, kind, target_id, lock=True)
        request_content = {"target_kind": kind, "target_id": str(target_id), "reason": reason}
        reviewed = None
        if expected_context is not None:
            if request_id is None:
                raise RevocationError("Reviewed revocations require request_id")
            reviewed = RevocationReviewContext.model_validate(expected_context).model_dump(mode="json")
            request_content["expected_context"] = reviewed
        existing = retry_result(self.db, ReleaseChainRevocation, request_id, "EVT-RCR-",
                                request_content, actor, RevocationError,
                                event_entity_id=target_id)
        if existing is not None:
            self.db.commit()
            return existing
        if not governance_state(self.db, kind, target_id)["eligible_for_new_work"]:
            raise RevocationError("Target is already revoked or blocked by an ancestor revocation")
        decision = effective_release_decision(self.db, context.release.id)
        if not decision or decision.decision != "RELEASE":
            raise RevocationError("Revocation requires an effective RELEASE decision")
        if reviewed is not None and reviewed != _review_context(context, kind, target_id, decision):
            raise RevocationError("Reviewed revocation context has changed or does not match the target")
        target_values = {"release_id": None, "delivery_package_id": None,
                         "distribution_id": None, "authorization_id": None}
        target_values[{"RELEASE": "release_id", "DELIVERY_PACKAGE": "delivery_package_id",
                       "DISTRIBUTION": "distribution_id", "AUTHORIZATION": "authorization_id"}[kind]] = target_id
        row = ReleaseChainRevocation(
            revocation_no=f"RCR-{(request_id or uuid.uuid4()).hex}", target_kind=kind,
            snapshot_id=decision.snapshot_id, release_decision_id=decision.id,
            reason=reason, revoked_by=actor.name, **target_values,
        )
        if request_id is not None:
            row.id = request_id
        self.db.add(row)
        commit_with_audit(self.db, lambda: {
            "event_no": f"EVT-RCR-{row.id.hex}", "event_type": "RELEASE_CHAIN_REVOCATION",
            "action": f"{kind.replace('DELIVERY_PACKAGE', 'DELIVERY')}_REVOKED",
            "entity_type": kind, "entity_id": target_id, "entity_ref": row.revocation_no,
            **actor.audit_fields(), "summary": f"{kind.replace('_', ' ').title()} revoked",
            "detail": reason, "occurred_at": row.revoked_at,
            "payload": {"revocation_id": str(row.id), "release_id": str(context.release.id),
                        "snapshot_id": str(row.snapshot_id), "release_decision_id": str(decision.id),
                        "reason": reason, "actor_source": actor.source,
                        **({"protocol_version": 1, "review_context": reviewed} if reviewed is not None else {}),
                        "request": request_content if request_id is not None else None},
        })
        self.db.refresh(row)
        return row
