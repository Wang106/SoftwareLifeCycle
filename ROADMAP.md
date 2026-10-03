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
- [ ] Retire or bound remaining unbounded compatibility lists after consumers migrate — deployment/authorization/distribution and exact delivery revision details now use bounded profiles/counts, paginated artifacts and catalog history; ASR downstream now uses fixed counts and exact authorization-release-scoped catalogs; ASR evidence now uses pinned Snapshot pagination; shared coverage, SSR and ASR component/policy reads now use SQL aggregates/bounded pages; exact detail/comparison and ASR passport now use bounded SQL pages; current readiness now uses SQL summaries and paginated approved exceptions; release catalogs/resolver and other rich profiles/domain catalogs remain

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

## ASR frozen policy consumer — 2026-10-03

ASR policy summary/full recording counts, independent artifact and recipient-rule pages
now pin exact Snapshot and artifact UUIDs, preserving declarations and internal-only
denial. Snapshot history already has bounded cursor pages; exact manifests/comparisons,
other policy/rich profiles, legacy catalogs and passport consumers still prevent checking
the remaining compatibility item. No checked item/denominator change: 34/44, Phase 4
8/9, Phase 6 3/5. Next address those exact frozen manifests, then passports, followed by
approved identity/session/controlled submission, result recovery/corrections and ops.
Conditional ranges remain 8–12 internal-use packages, 16–24 total production-review
packages; public staging stays read-only.

## Exact Snapshot detail migration and progress visibility — 2026-10-03

Exact detail now uses summary and independent bounded file/rule pages pinned by name
and UUID, full hashes, and exact search file selection. Comparison remains unbounded.
ROADMAP remains 34/44 (77%) because the Phase 4 acceptance item covers all remaining
compatibility consumers. [Read consumer tracking](docs/read-consumer-migration.md)
introduces 17 named scope groups: 11/17 at baseline 27ce7b7, 12/17 (71%) after this
package. This finer counter is new, equally weighted and not production readiness;
it does not change the ROADMAP denominator. Five remaining groups include broad
readiness/catalog/rich-profile work. Next comparison/passport/remaining reads, then
approved identity/session, authenticated submission/recovery/corrections and operations.
Conditional package ranges remain 8–12 internal-use / 16–24 total production-review.

## Snapshot comparison consumer migration — 2026-10-03

Comparison now uses an SQL summary and pinned bounded file differences, including
recipient-rule duplicate multiplicity and exact per-side rule links. No full manifest
consumer remains on this page; legacy API is retained. The same 17-group read ledger
advances 12/17 (71%) to 13/17 (76%). Four groups remain: passport, readiness/compatibility
policy, release catalogs/resolver, other rich profiles/domain catalogs. ROADMAP stays
34/44 (77%), Phase 4 8/9, Phase 6 3/5; no denominator change or production approval.
Next passport, then remaining reads; approved identity/session, authenticated submission/
recovery/corrections and operations follow. Remaining conditional planning ranges after
this package: 7–11 focused internal-use packages, 15–23 total production-review packages.

## ASR passport bounded consumer — 2026-10-03

Passport now uses fixed summary counts and four pinned bounded histories; exact
Snapshot UUID filtering survives missing metadata and historical selections cannot
release current content. The fixed 17-group ledger advances 13/17 (76%) → 14/17 (82%).
ROADMAP remains 34/44 (77%), Phase 4 8/9, Phase 6 3/5: remaining readiness/compatibility
policy, release catalogs/resolver and rich profiles/domain catalogs still span the
open read acceptance item. Next those three groups, then approved identity/session,
authenticated submission and recovery/corrections, operations. Conditional remaining
estimate: 6–10 focused packages toward internal use; 14–22 total toward production
review, subject to provider configuration and broad remaining group sizes.

## Bounded readiness and policy aggregation — 2026-10-03

The current readiness consumer now uses SQL policy/exception counts and a bounded
approved-exception page, preserving existing eight gates and live declaration semantics.
Current Snapshot pins fail closed after a newer commit. Group 15 closes under the same
consumer-based ledger rule; compatibility arrays/evaluate are retained and are not claimed
retired. Fine ledger 14/17 (82%) → 15/17 (88%). ROADMAP remains 34/44 (77%), Phase 4
8/9, Phase 6 3/5: release catalogs/resolver and rich profiles/domain catalogs remain.
Next release catalogs/exact legacy resolver, then remaining rich reads; approved identity/
session, authenticated submission/recovery/corrections and operations follow. Conditional
estimate: 5–9 packages toward internal use, 13–21 total toward production review.

## Release catalogs and exact legacy resolution — 2026-10-03

Mode: Codex cloud. Developed from GitHub main `12660a160750218e0997ecd322d652d6c36f1ea2`.
API 0.18.14 adds `/api/v1/release-catalog/application` and `/standard`, with
strict q/status/software_id/limit/offset filters, complete filtered counts and
stable created_at/UUID ordering. Page size is 1..100 (default 50), offset
0..100000. ASR latest Snapshot is a single SQL scalar projection; no growing
Snapshot/child arrays or ORM graph are fetched. Stored optional references are
outer joined and release rows survive missing metadata. The two frontend release
directories use these pages, keep filters in navigation, distinguish beyond-end
from unavailable, and retain default Chinese/selectable English and exact links.

`/api/v1/release-catalog/application/resolve?identifier=...` queries at most two
exact APPLICATION UUID-or-version matches. It returns unique/ambiguous/missing;
only unique supplies a release. UUID/version collisions stay ambiguous, without
UUID precedence or arbitrary selection. This fixes old links beyond the former
200-row directory cutoff; demo and unavailable/ambiguous fallbacks remain the
application directory. Legacy list APIs remain for compatibility, not retired.

No migration or write change; head remains `0018_asr_evidence_index`. Offset/count
reads are live observations, not a frozen cross-request dataset, authorization,
readiness or proof of release. Public staging remains read-only. Read consumer
ledger advances 15/17 (88%) to 16/17 (94%); ROADMAP remains 34/44 (77%) because
rich profiles/domain catalogs remain in group 17. Next review those consumers,
then approved OIDC/session, controlled submission/outcome recovery, broader
correction/revocation and operations. CI PR #1 (`438a663`) remains open and is
not counted as merged CI. Conditional planning: 4–8 focused packages toward
internal use, 12–20 total toward production review; group 17 may span packages.

## Bounded SCR and Issue directories — 2026-10-04 (Asia/Shanghai)

Mode: Codex cloud. Developed from GitHub main `665c0335d278125b748a4aa05e16ea0a5e60d9e2`.
API 0.18.15 adds strict bounded change-request and Issue catalogs. Both frontend
directories now retain filter context, complete totals, first/next links and explicit
beyond-end/unavailable states, with default Chinese/selectable English. SCR
verification/ready cards are SQL aggregates over the entire filtered set, preserving
previous case-sensitive status substring display semantics rather than redefining
release readiness. Exact UUID software/customer/project filters select stored SCR
fields only; Issue filters do not infer ownership/impact from version text. Literal
search escapes wildcard characters. Directory rows do not transfer Issue descriptions
or rich child histories; descriptions remain on exact profiles. Two scalar SQL
queries supply totals and a bounded window without growing ORM graphs/ID arrays.

No migration or write change; schema head stays `0018_asr_evidence_index`.
Legacy bulk `/changes` and `/issues` APIs and rich profiles remain compatible.
Offset pages/counts are mutable observations, not frozen evidence or write grants.
Public staging stays read-only. ROADMAP remains 34/44 (77%), read ledger 16/17
(94%): this package advances two directory consumers inside still-open group 17,
not that whole group's completion. Remaining: SCR details, Issue details/impact
evidence, supplier/customer/project directories and rich profiles, manufacturing
directories/profiles; then approved identity/session, controlled submission/recovery,
broader corrections/revocations and operations. CI PR #1 remains open. The prior
conditional package estimate is not reduced merely for finishing this partial group;
remaining rich reads need decomposition before a reliable new estimate.
