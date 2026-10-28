# Bounded nondeployment integration and reconciliation (P8)

## Genuine missing integration, not a new business policy

The P1/P2 suites exercise a real created DRAFT production authorization and dual-person
approval/history. Existing production/correction fixtures separately use seeded APPROVED
authorizations. They did not demonstrate the joined newly approved chain. This package
adds two domain integration scenarios, each run on SQLite and real PostgreSQL, using
existing services and existing fixtures. It changes no application service, permissions,
schema, gate, dependencies, provider configuration or production data.

1. Create DRAFT through the real authenticated creation service and verify creator audit;
   reject self-approval and preapproval deployment without side effects; approve with a
   different current same-project authority; create PENDING deployment and reject batch
   before MATCH; report exact expected software, create Changeover and Batch, append both
   corrections while preserving original rows and immutable release/snapshot; replay the
   same keys without new evidence; append authorization revocation; confirm original
   approval receipt as historical and reject **new deployment and new batch** without writes.
2. On the same real approved chain inject an audit failure after correction audit insertion;
   prove correction/baseline/audit transaction rollback and preserved original batch, then
   reuse the exact original key/body successfully once and replay without duplicates.

Upstream release approval/snapshot prerequisites are synthetic fixtures, but the tested
production authorization is never changed to APPROVED by seed or direct status patch.
These service-domain tests do not stand in for route authorization, real OIDC, browsers,
company deployment or physical flashing. Existing exact-target route/proxy denial,
concurrency and PostgreSQL migration/audit-trigger tests remain mandatory in complete CI.

Revocation is append-only chain governance, not necessarily a row status of REVOKED.
It does not retroactively erase an APPROVED historical receipt. Existing services do not
apply the same new-work gate to every historical actual report/changeover/correction;
this package neither bans those operations nor introduces a new business policy.
Imported-current correction baselines are IMPORTED_CORRECTED, not fabricated legacy facts.

## Current code versus external acceptance

| Area | Implemented evidence / code scope | Still not accepted or included |
|---|---|---|
| Production authorization | P1/P2 creation-to-dual-approval contract, exact context, explicit default-off UI, original historical receipt | Real personnel, issuer and browser/multiuser acceptance; old APPROVED is not re-certified |
| Fourteen command UI | Default-off confirmation/submission/results/original audit and manual cross-session recovery | Approved-target complete browser/identity acceptance, not just synthetic SSR/proxy tests |
| Private selectors | P3/P4 exact-target, minimal-role/field reads and explicit application | No global catalogue; unscoped Supplier/Customer stays manual; selecting is not authorization |
| Specialized histories/recovery | Batch/Changeover correction, registration, replacement and status manual recovery | Historical evidence is not current role/state, physical reversal or permission to write |
| Backup/recovery | Isolated synthetic PostgreSQL native rehearsal and safety tests | Target RPO/RTO, retention, restore/rollback rehearsal and company acceptance |
| Telemetry/incident handling | Existing opt-in content-free stdout observations, bounded offline evaluation and runbook | P7 channel/owner/retention decision, real collection/delivery/acknowledgment; no new adapter by assumption |
| Environments | Cloud sample/demo with existing gates | Approved independent test identity target, company network/data/deployment, actual Docker/offline runtime |
| Requirements outside this finite package | Resource references and AI extension boundary documented | Actual AI service deferred; VIN separately scoped; binary attachment storage/transfer not fully implemented |

P7 remains decision-blocked while P8 can finish its independent code/test/document scope.
No infinite enhancement queue is introduced. A future user decision may select a bounded
adapter, but this package neither chooses its recipient nor enables outgoing notifications.

## Document reconciliation and stopping condition

START_HERE and ROADMAP now put the latest finite work before historical local-CLI/old queue
entries. Controlled-write UI and finite-plan current tables distinguish implemented
selectors/submission/recovery from real acceptance; old dated evolution is preserved.
REQUIREMENTS explicitly retains AI/VIN/binary-storage and external acceptance boundaries.
No roadmap checkbox, denominator or acceptance percentage is increased for documentation
or synthetic integration alone: overall36/44=82%; modules100/100-demo/100-demo/100/89/60/17;
plans100/100/20/33/40/40/0. Current P8 full exact-head/main/provider evidence is separate.

After four real CI integration cases and complete protected-flow checks, report P8's
technical completion and P7's pending choice separately, then stop inventing further code
packages. Real operations, identity or deployment actions require their own approved target
and decisions. Unpublished detailed operational comments are not republished here through
an alternative file path.
