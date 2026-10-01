# Roadmap

This roadmap is evidence-based. Checked items exist in the current repository; unchecked items are proposals, not commitments or completed functionality. Priority may change through a `规划` handoff.

## Phase 1 — Domain foundation (complete)

- [x] Supplier, customer, project and software product records
- [x] Standard releases, application releases and component/artifact records
- [x] Software change requests, acceptance criteria, change points and issues
- [x] DVP plans/items/executions and release snapshots
- [x] PostgreSQL migrations and idempotent demo seed

## Phase 2 — Release governance (complete for demo scope)

- [x] Snapshot-bound readiness and verification views
- [x] Frozen artifact metadata and recipient distribution policy
- [x] Approval workflow history and release decisions
- [x] Snapshot history, exact manifests and comparisons
- [x] Application/standard release profiles, release matrix and software passport

## Phase 3 — Distribution and production trace (complete for demo scope)

- [x] Delivery package revisions and artifact selection
- [x] Distribution receipts and production authorization scope
- [x] Deployment expected/actual software provenance
- [x] Software changeovers and production batch trace
- [x] Exact downstream trace from release to batch

## Phase 4 — Evidence, review and auditability (current baseline)

- [x] Append-only formal activity ledger
- [x] Snapshot-bound issue impact evidence and judgments
- [x] Explicit acceptance-criterion-to-DVP assignments
- [x] Purpose-limited test releases
- [x] Append-only external resource references
- [x] Bounded catalogs for DVP, distribution, production, governance and audit history
- [x] Atomic audit events for current governance and distribution service writes
- [x] Inventory every write path and enforce explicit audit/idempotency/concurrency review in tests
- [ ] Retire or bound remaining unbounded compatibility lists after consumers migrate

## Phase 5 — Identity and authorization (current foundation)

- [x] Define provider-neutral user/service principals, global roles, software membership and project membership
- [x] Add configurable OIDC Bearer validation and ACTIVE local-principal resolution without storing tokens
- [ ] Select/configure the approved OIDC issuer, audience and JWKS endpoint in a target environment
- [x] Enforce exact project/software/resource authorization on every current write route
- [x] Add denial tests for wrong project, wrong software, insufficient role and suspended membership
- [x] Bind atomically audited writes to authenticated principals while preserving request declarations
- [x] Add atomic authenticated audit events to snapshot and production command paths
- [x] Define admin, reviewer, release authority, distribution authority and production roles
- [x] Keep the public demo read-only until the security acceptance criteria pass

Exit gate: protected operations reject unauthenticated and out-of-scope actors; positive and negative integration tests pass; security decisions are documented.

## Phase 6 — Controlled write experience (two safety slices implemented)

- [ ] Prioritize which existing command APIs require UI forms
- [ ] Add idempotency keys and explicit conflict behavior where absent — Snapshot, Batch, Approval Action and Release Decision implemented; six routes remain pending
- [ ] Add concurrency protection for approval and other state transitions — Release numbering, shared Batch quota and approval/decision transitions implemented; six routes remain pending
- [ ] Provide correction/revocation flows using new history records, not destructive edits
- [ ] Add validation, confirmation and trace links to every write result

Exit gate: every exposed write is authorized, auditable, retry-safe where required and covered by end-to-end tests.

## Phase 7 — Production operations

- [ ] Add CI for backend tests, migration validation and frontend production build
- [ ] Add supported backup/restore, retention and disaster-recovery procedures
- [ ] Define metrics, structured logs, alerting and incident runbooks
- [ ] Separate demo, staging and company environments and disable seed in non-demo databases
- [ ] Establish an approved network path between frontend, API and company data
- [ ] Load real data only after privacy, security and authorization review

Exit gate: an operational readiness review confirms repeatable deploy/rollback, monitoring, recovery and data governance.

## How to change this roadmap

Use `规划：<目标>` to agree on scope and acceptance criteria. A roadmap item moves to complete only when its implementation and verification are present in `main`; discussion, demo data or a UI label alone is insufficient.

## Current measurable progress and remaining sequence

Checked roadmap items remain 31/44 (70%): Phase 1 5/5, Phase 2 5/5 (demo),
Phase 3 5/5 (demo), Phase 4 8/9, Phase 5 8/9, Phase 6 0/5 and Phase 7 0/6.
Phase 6 broad items remain partial; 8/14 write routes (57%) now declare request-ID
and row-lock controls, while all 14 declare exact scope, actor binding and atomic audit.

1. Add retry/transaction protection to delivery, distribution, authorization,
   deployment and changeover; define actual-software optimistic concurrency.
2. Define append-only correction/revocation and result validation/confirmation/trace;
   select controlled UI forms without opening public staging writes.
3. Migrate consumers from unbounded compatibility lists to bounded catalogs.
4. Configure an approved OIDC provider, provider-backed tests, grant administration
   and browser login/session flow before exposing protected multi-user workflows.
5. Add CI backend/PostgreSQL/migration/frontend checks; backup/restore, retention,
   monitoring, alerts and incident procedures.
6. Separate demo/staging/company environments, disable non-demo seed, approve
   network/data governance and validate recovery before loading real company data.
