# Database

## Current baseline

- Engine: PostgreSQL 16 in the local Compose environment.
- ORM: SQLAlchemy 2.
- Migration tool: Alembic.
- Required schema revision: `0015_identity_roles`.
- Local demo startup: migrations, optional idempotent Seed, then API.
- Production/company rule: use a fresh database and `SEED_ON_STARTUP=false`.

SQLite is used by isolated tests where supported, but it does not validate PostgreSQL JSONB or database triggers. PostgreSQL is required for schema and append-only-rule verification.

## Table groups

| Domain | Main tables |
| --- | --- |
| Organization/software | `suppliers`, `customers`, `projects`, `software_products` |
| Release definition | `releases`, `standard_release_details`, `application_release_details`, `component_definitions`, `release_components`, `artifacts` |
| Change/issue | `software_change_requests`, `acceptance_criteria`, `change_points`, `issues`, `issue_change_request_relations` |
| Verification | `dvp_plans`, `dvp_items`, `change_point_dvp_items`, `issue_dvp_items`, `test_releases`, `dvp_executions`, `acceptance_dvp_links` |
| Frozen evidence/policy | `release_snapshots`, `snapshot_artifacts`, `artifact_distribution_rules`, `snapshot_artifact_distribution_rules`, `policy_exceptions`, `issue_impact_assessments`, `resource_links` |
| Governance | `approval_requests`, `approval_steps`, `approval_actions`, `release_decisions`, `audit_events` |
| Distribution | `delivery_packages`, `delivery_package_items`, `distributions`, `software_authorizations` |
| Production | `manufacturing_sites`, `production_lines`, `deployments`, `software_changeovers`, `production_batches` |
| Identity/authorization foundation | `security_principals`, `global_role_assignments`, `software_memberships`, `project_memberships` |

## Key relationship path

```text
Supplier -> SoftwareProduct -> Release
Customer -> Project -> ApplicationReleaseDetail -> Release
Release -> ReleaseComponent -> Artifact
Release -> ReleaseSnapshot -> SnapshotArtifact

SoftwareChangeRequest -> AcceptanceCriterion / ChangePoint
SoftwareChangeRequest <-> Issue
SoftwareChangeRequest -> DvpPlan -> DvpItem -> DvpExecution
Release + Snapshot -> TestRelease / DvpExecution / ImpactAssessment

Release + Snapshot -> ApprovalRequest -> ReleaseDecision
Release + Snapshot -> DeliveryPackage -> Distribution -> SoftwareAuthorization
SoftwareAuthorization -> Deployment -> SoftwareChangeover / ProductionBatch
```

Foreign keys and stored UUIDs are the trace authority. Display numbers, versions and names help navigation but must not be used to infer a formal relationship.

## Frozen and append-only records

- `release_snapshots` and `snapshot_artifacts` hold frozen release metadata/artifact evidence.
- `snapshot_artifact_distribution_rules` preserve recipient decisions at freeze time.
- `audit_events`, `issue_impact_assessments`, `acceptance_dvp_links` and `resource_links` have PostgreSQL triggers rejecting UPDATE and DELETE.
- Corrections to append-only facts are represented by new records. Do not add application code that mutates these tables.

## Migration history

| Revision | Capability |
| --- | --- |
| `0001`–`0003` | Core releases/snapshots, change/testing and policy exceptions |
| `0004`–`0005` | Artifact distribution rules and frozen snapshot policies |
| `0006` | Approval and release decisions |
| `0007`–`0008` | Delivery/distribution/authorization and distribution binding |
| `0009` | Production traceability |
| `0010` | Append-only audit events |
| `0011` | Optional constrained customer region |
| `0012` | Append-only issue impact assessments |
| `0013` | Append-only acceptance-to-DVP links |
| `0014` | Append-only external resource links |
| `0015` | Provider-neutral user/service principals and scoped role grants |

Revision `0015` stores only external identity references and grants. It deliberately contains no password, token or client-secret columns, and no Seed identities or grants are created.

Never edit an applied migration to change history. Add a new ordered revision, import its model metadata in Alembic as required, and update `required_db_revision` in `backend/app/core/config.py` together with deployment documentation and readiness tests.

## Data handling rules

- The public environment is sample/test only; never load company or customer-sensitive data there.
- `DATABASE_URL` belongs only in the API environment, not frontend public variables or Git.
- Demo Seed is idempotent for named sample records but is not a production provisioning process.
- Backup, restore, retention and disaster-recovery procedures are not yet defined and are roadmap items.
- Before a company deployment, add authentication/authorization, review classifications and access rules, disable Seed and validate the complete migration chain on a fresh PostgreSQL database.
