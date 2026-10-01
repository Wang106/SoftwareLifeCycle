"""Explicit security and consistency inventory for every registered write route.

This module is descriptive: it does not grant access or replace runtime guards.
Tests keep the inventory synchronized with FastAPI so a new write route cannot be
added without an explicit review of identity, authorization, audit, idempotency
and concurrency behavior.
"""

from dataclasses import dataclass
from typing import Literal

from app.security_roles import ALL_ROLES


ActorSource = Literal["NONE", "DECLARED_OPTIONAL", "DECLARED_REQUIRED"]
AuditGuarantee = Literal["NONE", "ATOMIC_APPEND"]
IdempotencyGuarantee = Literal["NONE", "REQUEST_ID"]
ConcurrencyGuarantee = Literal["NONE", "ROW_LOCK"]


@dataclass(frozen=True)
class WriteContract:
    operation: str
    scope: str
    actor_source: ActorSource
    audit: AuditGuarantee
    idempotency: IdempotencyGuarantee
    concurrency: ConcurrencyGuarantee
    planned_roles: frozenset[str]
    known_gap: str
    authentication: Literal["NONE"] = "NONE"
    authorization: Literal["NONE"] = "NONE"
    public_exposure: Literal["READ_ONLY_BLOCKED"] = "READ_ONLY_BLOCKED"


WRITE_CONTRACTS: dict[tuple[str, str], WriteContract] = {
    ("POST", "/api/v1/releases/{release_id}/create-snapshot"): WriteContract(
        operation="Freeze release snapshot",
        scope="release",
        actor_source="NONE",
        audit="NONE",
        idempotency="NONE",
        concurrency="NONE",
        planned_roles=frozenset({"SOFTWARE_MAINTAINER", "CONTRIBUTOR"}),
        known_gap="No actor, audit event, idempotency key or release row lock.",
    ),
    ("POST", "/api/v1/approvals/{approval_no}/actions"): WriteContract(
        operation="Record approval action",
        scope="approval target and active step",
        actor_source="DECLARED_REQUIRED",
        audit="ATOMIC_APPEND",
        idempotency="NONE",
        concurrency="NONE",
        planned_roles=frozenset({"REVIEWER"}),
        known_gap="Declared actor is untrusted; active approval/step rows are not locked.",
    ),
    ("POST", "/api/v1/approvals/{approval_no}/release-decision"): WriteContract(
        operation="Record release decision",
        scope="approval release and frozen snapshot",
        actor_source="DECLARED_REQUIRED",
        audit="ATOMIC_APPEND",
        idempotency="NONE",
        concurrency="NONE",
        planned_roles=frozenset({"RELEASE_AUTHORITY"}),
        known_gap="Declared actor is untrusted; approval is not locked against concurrent decisions.",
    ),
    ("POST", "/api/v1/deliveries"): WriteContract(
        operation="Create delivery package revision",
        scope="release, snapshot, recipient and selected artifacts",
        actor_source="DECLARED_OPTIONAL",
        audit="ATOMIC_APPEND",
        idempotency="NONE",
        concurrency="NONE",
        planned_roles=frozenset({"DISTRIBUTION_AUTHORITY"}),
        known_gap="Actor is optional; retries use duplicate rejection rather than an idempotency key.",
    ),
    ("POST", "/api/v1/distributions"): WriteContract(
        operation="Record distribution",
        scope="delivery package and recipient",
        actor_source="NONE",
        audit="ATOMIC_APPEND",
        idempotency="NONE",
        concurrency="NONE",
        planned_roles=frozenset({"DISTRIBUTION_AUTHORITY"}),
        known_gap="Audit records an unavailable actor; no idempotency or locking guarantee.",
    ),
    ("POST", "/api/v1/authorizations"): WriteContract(
        operation="Create production authorization",
        scope="distribution, release, snapshot, customer, project, site and line",
        actor_source="NONE",
        audit="ATOMIC_APPEND",
        idempotency="NONE",
        concurrency="NONE",
        planned_roles=frozenset({"PRODUCTION_AUTHORITY"}),
        known_gap="Audit records an unavailable actor; creation does not authenticate an authority.",
    ),
    ("POST", "/api/v1/deployments"): WriteContract(
        operation="Create deployment expectation",
        scope="authorization and production line",
        actor_source="NONE",
        audit="NONE",
        idempotency="NONE",
        concurrency="NONE",
        planned_roles=frozenset({"PRODUCTION_OPERATOR"}),
        known_gap="No actor, audit event, idempotency key or scope row locks.",
    ),
    ("POST", "/api/v1/deployments/{deployment_no}/actual"): WriteContract(
        operation="Report actual deployed software",
        scope="deployment, release and snapshot",
        actor_source="NONE",
        audit="NONE",
        idempotency="NONE",
        concurrency="NONE",
        planned_roles=frozenset({"PRODUCTION_OPERATOR"}),
        known_gap="Mutable overwrite has no actor, append-only audit event or optimistic lock.",
    ),
    ("POST", "/api/v1/deployments/{deployment_no}/changeovers"): WriteContract(
        operation="Record software changeover",
        scope="deployment and source/target release",
        actor_source="NONE",
        audit="NONE",
        idempotency="NONE",
        concurrency="NONE",
        planned_roles=frozenset({"PRODUCTION_OPERATOR"}),
        known_gap="No actor, audit event, idempotency key or deployment row lock.",
    ),
    ("POST", "/api/v1/deployments/{deployment_no}/batches"): WriteContract(
        operation="Create production batch",
        scope="deployment, authorization and optional changeover",
        actor_source="NONE",
        audit="NONE",
        idempotency="NONE",
        concurrency="NONE",
        planned_roles=frozenset({"PRODUCTION_OPERATOR"}),
        known_gap="Batch-limit check is not serialized; no actor or audit event is recorded.",
    ),
    ("POST", "/api/v1/issues/{issue_no}/impact-assessments"): WriteContract(
        operation="Append issue impact assessment",
        scope="issue, release and frozen snapshot",
        actor_source="DECLARED_REQUIRED",
        audit="ATOMIC_APPEND",
        idempotency="REQUEST_ID",
        concurrency="ROW_LOCK",
        planned_roles=frozenset({"REVIEWER"}),
        known_gap="Declared actor is untrusted; no project authorization is enforced.",
    ),
    ("POST", "/api/v1/changes/{request_no}/acceptance-dvp-links"): WriteContract(
        operation="Append acceptance-to-DVP assignment",
        scope="software change request, criterion and DVP item",
        actor_source="DECLARED_REQUIRED",
        audit="ATOMIC_APPEND",
        idempotency="REQUEST_ID",
        concurrency="ROW_LOCK",
        planned_roles=frozenset({"CONTRIBUTOR"}),
        known_gap="Declared actor is untrusted; no project authorization is enforced.",
    ),
    ("POST", "/api/v1/testing/releases"): WriteContract(
        operation="Create purpose-limited test release draft",
        scope="release and frozen snapshot",
        actor_source="DECLARED_REQUIRED",
        audit="ATOMIC_APPEND",
        idempotency="REQUEST_ID",
        concurrency="ROW_LOCK",
        planned_roles=frozenset({"CONTRIBUTOR"}),
        known_gap="Declared actor is untrusted; no project authorization is enforced.",
    ),
    ("POST", "/api/v1/resources"): WriteContract(
        operation="Append external resource reference",
        scope="referenced lifecycle entity",
        actor_source="DECLARED_REQUIRED",
        audit="ATOMIC_APPEND",
        idempotency="REQUEST_ID",
        concurrency="ROW_LOCK",
        planned_roles=frozenset({"CONTRIBUTOR"}),
        known_gap="Declared actor is untrusted; registering a location does not verify access.",
    ),
}
