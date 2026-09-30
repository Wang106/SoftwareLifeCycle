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
- [ ] Inventory every remaining write path and define its audit/idempotency/concurrency guarantee
- [ ] Retire or bound remaining unbounded compatibility lists after consumers migrate

## Phase 5 — Identity and authorization (recommended next)

- [ ] Approve an identity model: user, organization, role, project membership and service identity
- [ ] Add authentication without placing secrets or tokens in lifecycle records
- [ ] Enforce customer/project/resource authorization in the API and test denial paths
- [ ] Bind new audit actors to authenticated principals while preserving historical declared actors
- [ ] Define admin, reviewer, release authority, distribution authority and production roles
- [ ] Keep the public demo read-only until the security acceptance criteria pass

Exit gate: protected operations reject unauthenticated and out-of-scope actors; positive and negative integration tests pass; security decisions are documented.

## Phase 6 — Controlled write experience

- [ ] Prioritize which existing command APIs require UI forms
- [ ] Add idempotency keys and explicit conflict behavior where absent
- [ ] Add concurrency protection for approval and other state transitions
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
