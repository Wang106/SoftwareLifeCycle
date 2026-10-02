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
- [ ] Retire or bound remaining unbounded compatibility lists after consumers migrate — deployment/authorization/distribution and exact delivery revision details now use bounded profiles/counts, paginated artifacts and catalog history; ASR downstream now uses fixed counts and exact authorization-release-scoped catalogs; ASR evidence now uses pinned Snapshot pagination; ASR profile coverage, SSR and other consumers remain

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

## Phase 6 — Controlled write experience (safety slices and all 14 request-preparation forms implemented)

- [x] Prioritize which existing command APIs require UI forms — all 14 are grouped in docs/controlled-write-ui.md; Snapshot/actual/Batch/Approval Action/Release Decision/Impact/Acceptance-to-DVP/Resource/Delivery/Distribution/Authorization/Test Release/Deployment/Changeover request preparation is implemented, authenticated submission remains pending
- [x] Add idempotency keys and explicit conflict behavior where absent — all 14 current command routes support request-ID contracts; optional no-key legacy semantics remain documented
- [x] Add concurrency protection for approval and other state transitions — all 14 current routes serialize their command scope; actual reports add expected-version conflicts for keyed calls
- [ ] Provide correction/revocation flows using new history records, not destructive edits — actual-report corrections append full before/after audit; other lifecycle correction/revocation workflows remain
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

Checked roadmap items are now 34/44 (77%): Phase 1 5/5, Phase 2 5/5 (demo),
Phase 3 5/5 (demo), Phase 4 8/9, Phase 5 8/9, Phase 6 3/5 (60%) and Phase 7 0/6.
All 14 write routes declare request-ID, row serialization, exact scope, trusted actor
and atomic audit. Actual keyed reports require expected_version and replacement
reason. Legacy no-key paths remain compatible and weaker; broad correction/revocation,
UI and result confirmation/trace are incomplete. These percentages are checked scope,
not provider configuration or production-readiness certification.

1. All 14 preparation forms are implemented; configure approved identity/session
   and a controlled target before adding authenticated submission.
2. Connect first request-preparation forms to approved identity/session and define
   authenticated submission, uncertain-result recovery and successful result trace;
   keep public staging read-only and use a separately approved controlled target.
3. Extend append-only correction/revocation contracts beyond actual reporting;
   never infer physical flashing reversal or alter existing batch history.
4. Continue migrating consumers from unbounded compatibility lists/details to bounded catalogs; deployment/authorization/distribution and exact delivery revision and ASR downstream migrations are implemented; ASR evidence is now paginated; ASR profile coverage and SSR consumers remain.
5. Configure an approved OIDC provider, provider-backed tests, audited grant
   administration and browser login/session flow before protected multi-user use.
6. Add CI backend/PostgreSQL/migration/frontend checks; backup/restore, retention,
   monitoring, alerts and incident procedures.
7. Separate demo/staging/company environments, disable non-demo seed, approve
   network/data governance and validate recovery before loading company data.

## Bilingual UI and planning estimate — 2026-10-02

The additional bilingual requirement covers all 63 current pages and 14 forms, with
default Chinese, remembered English selection and unchanged command semantics.
The original roadmap denominator remains 44; Phase 6 stays 3/5 and overall 34/44.

Estimated remaining focused development packages: **8–12 to controlled internal use**;
**16–24 total to a production-ready review**, including those initial packages. These
are planning ranges, not release commitments. Identity/provider approvals, a controlled
non-public environment, correction policy and real data/network decisions can expand
the scope. One package should deliver one testable behavior and its verification.

Suggested package groups: remaining bounded consumers (1–2); approved OIDC/session and
controlled target (2–3); authenticated submission, uncertain-result recovery and result
trace for all forms (3–4); append-only corrections/revocations (2–3); CI, environment
separation, monitoring, backups/restore drills and security/data acceptance (8–12).
Several groups can overlap, so these are not mechanically additive. Never enable
public staging writes to satisfy a submission milestone.

## Coverage consumer migration — 2026-10-02

The shared release coverage service now returns SQL aggregates with exact release/
Snapshot scope and preserved project/set/any-PASS semantics. No child history or growing
ID arrays are transferred. This advances the unchecked compatibility-consumer item;
remaining SSR/components/policy/snapshot/history reads still prevent its completion.
No checked items or denominator change: 34/44 overall, Phase 4 8/9, Phase 6 3/5.
Next package: continue those remaining consumers; planning ranges above remain conditional.

## SSR consumer migration — 2026-10-02

SSR overview now reads a fixed parent summary and two bounded projections for components
and stored baseline users. This advances the remaining compatibility-consumer item but
does not complete it: ASR component declarations, policy/snapshot/history/passport reads
remain. No checked item/denominator changes; overall 34/44, Phase 4 8/9, Phase 6 3/5.
Next package should address those ASR component/baseline declarations; planning ranges
above remain conditional rather than deployment commitments.

## ASR component consumer migration — 2026-10-02

ASR component declarations and unlinked baseline components now use exact summary and
independent bounded pages with preserved stored-link semantics and default Chinese/
English controls. Remaining policy/snapshot/history/passport consumers keep Phase 4's
compatibility migration unchecked. No checked item or denominator changes: 34/44,
Phase 4 8/9, Phase 6 3/5. Next continue these reads, then approved identity/session,
controlled target and authenticated submission/recovery/corrections/operations.
Conditional estimates remain 8–12 internal-use packages, 16–24 total production-review
packages; no write enablement on public staging.
