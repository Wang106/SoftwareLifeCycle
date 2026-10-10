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
    authentication: Literal["OIDC_WHEN_ENABLED"] = "OIDC_WHEN_ENABLED"
    authorization: Literal["SCOPED_WHEN_OIDC"] = "SCOPED_WHEN_OIDC"
    actor_binding: Literal["AUTHENTICATED_WHEN_OIDC", "NO_ACTOR_SINK"] = "AUTHENTICATED_WHEN_OIDC"
    public_exposure: Literal["READ_ONLY_BLOCKED"] = "READ_ONLY_BLOCKED"


WRITE_CONTRACTS: dict[tuple[str, str], WriteContract] = {
    ("POST", "/api/v1/releases/{release_id}/create-snapshot"): WriteContract(
        operation="Freeze release snapshot",
        scope="release",
        actor_source="NONE",
        audit="ATOMIC_APPEND",
        idempotency="REQUEST_ID",
        concurrency="ROW_LOCK",
        planned_roles=frozenset({"SOFTWARE_MAINTAINER", "CONTRIBUTOR"}),
        known_gap="Legacy requests without request_id intentionally create a new snapshot.",
    ),
    ("POST", "/api/v1/approvals/{approval_no}/actions"): WriteContract(
        operation="Record approval action",
        scope="approval target and active step",
        actor_source="DECLARED_REQUIRED",
        audit="ATOMIC_APPEND",
        idempotency="REQUEST_ID",
        concurrency="ROW_LOCK",
        planned_roles=frozenset({"REVIEWER"}),
        known_gap="Legacy actions without expected_step_id still target the current step.",
    ),
    ("POST", "/api/v1/approvals/{approval_no}/release-decision"): WriteContract(
        operation="Record release decision",
        scope="approval release and frozen snapshot",
        actor_source="DECLARED_REQUIRED",
        audit="ATOMIC_APPEND",
        idempotency="REQUEST_ID",
        concurrency="ROW_LOCK",
        planned_roles=frozenset({"RELEASE_AUTHORITY"}),
        known_gap="Distinct decision numbers remain append-only history; no correction/revocation command.",
    ),
    ("POST", "/api/v1/deliveries"): WriteContract(
        operation="Create delivery package revision",
        scope="release, snapshot, recipient and selected artifacts",
        actor_source="DECLARED_OPTIONAL",
        audit="ATOMIC_APPEND",
        idempotency="REQUEST_ID",
        concurrency="ROW_LOCK",
        planned_roles=frozenset({"DISTRIBUTION_AUTHORITY"}),
        known_gap="Legacy no-key clients reject duplicate business numbers; no correction/revocation command.",
    ),
    ("POST", "/api/v1/distributions"): WriteContract(
        operation="Record distribution",
        scope="delivery package and recipient",
        actor_source="NONE",
        audit="ATOMIC_APPEND",
        idempotency="REQUEST_ID",
        concurrency="ROW_LOCK",
        planned_roles=frozenset({"DISTRIBUTION_AUTHORITY"}),
        known_gap="Legacy no-key clients reject duplicate business numbers; no correction/revocation command.",
    ),
    ("POST", "/api/v1/authorizations"): WriteContract(
        operation="Create production authorization",
        scope="distribution, release, snapshot, customer, project, site and line",
        actor_source="NONE",
        audit="ATOMIC_APPEND",
        idempotency="REQUEST_ID",
        concurrency="ROW_LOCK",
        planned_roles=frozenset({"PRODUCTION_AUTHORITY"}),
        known_gap="Legacy no-key clients reject duplicate business numbers; no correction/revocation command.",
    ),
    ("POST", "/api/v1/deployments"): WriteContract(
        operation="Create deployment expectation",
        scope="authorization and production line",
        actor_source="NONE",
        audit="ATOMIC_APPEND",
        idempotency="REQUEST_ID",
        concurrency="ROW_LOCK",
        planned_roles=frozenset({"PRODUCTION_OPERATOR"}),
        known_gap="Legacy no-key calls reject duplicate numbers; no authorization/line transition API.",
    ),
    ("POST", "/api/v1/deployments/{deployment_no}/actual"): WriteContract(
        operation="Report actual deployed software",
        scope="deployment, release and snapshot",
        actor_source="NONE",
        audit="ATOMIC_APPEND",
        idempotency="REQUEST_ID",
        concurrency="ROW_LOCK",
        planned_roles=frozenset({"PRODUCTION_OPERATOR"}),
        known_gap="Keyed reports require expected_version and correction reasons; legacy no-key overwrites remain compatible.",
    ),
    ("POST", "/api/v1/deployments/{deployment_no}/changeovers"): WriteContract(
        operation="Record software changeover",
        scope="deployment and source/target release",
        actor_source="NONE",
        audit="ATOMIC_APPEND",
        idempotency="REQUEST_ID",
        concurrency="ROW_LOCK",
        planned_roles=frozenset({"PRODUCTION_OPERATOR"}),
        known_gap="Distinct changeover numbers retain history; no correction/revocation command.",
    ),
    ("POST", "/api/v1/deployments/{deployment_no}/batches"): WriteContract(
        operation="Create production batch",
        scope="deployment, authorization and optional changeover",
        actor_source="NONE",
        audit="ATOMIC_APPEND",
        idempotency="REQUEST_ID",
        concurrency="ROW_LOCK",
        planned_roles=frozenset({"PRODUCTION_OPERATOR"}),
        known_gap="Legacy requests without request_id retain duplicate-number rejection.",
    ),
    ("POST", "/api/v1/issues/{issue_no}/impact-assessments"): WriteContract(
        operation="Append issue impact assessment",
        scope="issue, release and frozen snapshot",
        actor_source="DECLARED_REQUIRED",
        audit="ATOMIC_APPEND",
        idempotency="REQUEST_ID",
        concurrency="ROW_LOCK",
        planned_roles=frozenset({"REVIEWER"}),
        known_gap="Explicit current-predecessor corrections preserve history; withdrawal and controlled correction UI remain pending.",
    ),
    ("POST", "/api/v1/changes/{request_no}/acceptance-dvp-links"): WriteContract(
        operation="Append acceptance-to-DVP assignment",
        scope="software change request, criterion and DVP item",
        actor_source="DECLARED_REQUIRED",
        audit="ATOMIC_APPEND",
        idempotency="REQUEST_ID",
        concurrency="ROW_LOCK",
        planned_roles=frozenset({"CONTRIBUTOR"}),
        known_gap="Current-predecessor replacement/withdrawal preserve assignment history; controlled correction UI and real acceptance remain pending.",
    ),
    ("POST", "/api/v1/testing/releases"): WriteContract(
        operation="Create purpose-limited test release draft",
        scope="release and frozen snapshot",
        actor_source="DECLARED_REQUIRED",
        audit="ATOMIC_APPEND",
        idempotency="REQUEST_ID",
        concurrency="ROW_LOCK",
        planned_roles=frozenset({"CONTRIBUTOR"}),
        known_gap="The draft lifecycle has no activation/supersession/revocation commands.",
    ),
    ("POST", "/api/v1/resources"): WriteContract(
        operation="Append external resource reference",
        scope="referenced lifecycle entity",
        actor_source="DECLARED_REQUIRED",
        audit="ATOMIC_APPEND",
        idempotency="REQUEST_ID",
        concurrency="ROW_LOCK",
        planned_roles=frozenset({"CONTRIBUTOR"}),
        known_gap="Registering a location does not verify that it exists or is accessible.",
    ),
}


@dataclass(frozen=True)
class SessionControlContract:
    operation: str
    authentication: str = 'OIDC_REQUIRED'
    authorization: str = 'ACTIVE_USER_SELF_AND_TOKEN'
    public_exposure: str = 'AUTHENTICATED_METADATA_ONLY'
    audit: str = 'ATOMIC_APPEND'
    concurrency: str = 'PRINCIPAL_ROW_LOCK'
    idempotency: str = 'SESSION_ID'


# These metadata controls have a narrow read-only exception; all business commands
# remain READ_ONLY_BLOCKED. Keeping both inventories exhaustive catches route drift.
SESSION_CONTROL_CONTRACTS = {
    ('POST', '/api/v1/security/me/browser-sessions'): SessionControlContract('Register own browser session'),
    ('POST', '/api/v1/security/me/browser-sessions/{session_id}/revoke'): SessionControlContract('Revoke own browser session'),
}


@dataclass(frozen=True)
class AdminControlContract:
    operation: str
    authentication: str = 'OIDC_REQUIRED'
    authorization: str = 'ACTIVE_PLATFORM_ADMIN'
    actor_binding: str = 'AUTHENTICATED_PRINCIPAL'
    public_exposure: str = 'READ_ONLY_BLOCKED'
    audit: str = 'ATOMIC_APPEND'
    concurrency: str = 'ADMIN_TRANSACTION_GATE_AND_PRINCIPAL_GRANT_AND_MEMBERSHIP_ROW_LOCK'
    idempotency: str = 'EVENT_NO_EXACT_REQUEST_AND_ADMIN'
    precondition: str = 'EXPECTED_MEMBERSHIP_STATUS'


# Authorization administration is separate from the fixed14 domain commands and
# from own-session metadata. It has no read-only or auth-disabled exception.
ADMIN_CONTROL_CONTRACTS = {
    ('POST', '/api/v1/security/admin/global-roles'):
        AdminControlContract('Register a suspended exact global role',
            concurrency='ADMIN_TRANSACTION_GATE_AND_RECIPIENT_ROW_LOCK_AND_UNIQUENESS',
            precondition='ACTIVE_CONFIGURED_ISSUER_RECIPIENT_AND_NEW_GLOBAL_ROLE'),
    ('POST', '/api/v1/security/admin/global-roles/{grant_id}/status'):
        AdminControlContract('Suspend or resume a global role with last-admin protection',
            concurrency='ADMIN_TRANSACTION_GATE_AND_PRINCIPAL_GRANT_ROW_LOCK',
            precondition='EXPECTED_GLOBAL_ROLE_STATUS_AND_RETAIN_EFFECTIVE_ADMIN'),
    ('POST', '/api/v1/security/admin/memberships/{scope}'):
        AdminControlContract('Register a suspended exact project/software role for a non-admin principal',
            concurrency='ADMIN_TRANSACTION_GATE_AND_ADMIN_GRANT_AND_RECIPIENT_PRINCIPAL_ROW_LOCK_AND_UNIQUENESS',
            precondition='ACTIVE_CONFIGURED_ISSUER_NON_ADMIN_RECIPIENT_AND_NEW_EXACT_ROLE'),
    ('POST', '/api/v1/security/admin/principals'):
        AdminControlContract('Register a disabled local identity without grants',
            concurrency='ADMIN_TRANSACTION_GATE_AND_ADMIN_PRINCIPAL_GRANT_LOCK_AND_IDENTITY_UNIQUENESS',
            precondition='CONFIGURED_ISSUER_AND_NEW_UUID_AND_SUBJECT'),
    ('POST', '/api/v1/security/admin/principals/{principal_id}/status'):
        AdminControlContract('Enable or disable a non-platform-admin local principal',
            concurrency='ADMIN_TRANSACTION_GATE_AND_ADMIN_GRANT_AND_TARGET_PRINCIPAL_ROW_LOCK',
            precondition='EXPECTED_PRINCIPAL_STATUS_AND_NO_PLATFORM_ADMIN_GRANT'),
    ('POST', '/api/v1/security/admin/memberships/{scope}/{membership_id}/status'):
        AdminControlContract('Suspend or resume an existing project/software membership'),
}


@dataclass(frozen=True)
class OperatorControlContract:
    operation: str
    authorization: str = 'EXPLICIT_LOCAL_PROCESS_AND_DATABASE_PRIVILEGES'
    authentication: str = 'INFRASTRUCTURE_CONTEXT_NOT_OIDC_HUMAN'
    public_exposure: str = 'NO_HTTP_ROUTE_OR_STARTUP_INVOCATION'
    audit: str = 'ATOMIC_APPEND'
    concurrency: str = 'ADMIN_TRANSACTION_GATE_AND_PRINCIPAL_GRANT_ROW_LOCK'
    idempotency: str = 'EVENT_NO_EXACT_REQUEST_TARGET_AND_OPERATOR'
    precondition: str = 'OPERATOR_ENABLED_WRITABLE_CONFIGURED_OIDC_ZERO_EFFECTIVE_ADMINS'
    target_binding: str = 'DATABASE_SCHEMA_ROLE_AND_PROVIDER_FINGERPRINT'
    approval_reference: str = 'DECLARED_EXTERNAL_APPROVAL_NOT_AUTOMATICALLY_VERIFIED'


# Offline operator controls are intentionally outside the exhaustive HTTP inventory.
OPERATOR_CONTROL_CONTRACTS = {
    'bootstrap': OperatorControlContract('Create first local USER administrator only without any prior admin assignments'),
    'recover': OperatorControlContract('Restore an existing local USER administrator only while no effective admin remains'),
}
