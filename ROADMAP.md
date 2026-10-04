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
- [ ] Retire or bound remaining unbounded compatibility lists after consumers migrate — all 17 identified read-consumer groups now use bounded reads, including manufacturing site directory/detail. API 0.18.22 has retired 19 reviewed organization/manufacturing/production/distribution GET routes; other bulk/rich families remain pending caller review and retirement/explicit bounds. See docs/compatibility-read-retirement.md. Consumer migration alone does not satisfy this endpoint acceptance item.

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
4. All 17 identified read-consumer groups are migrated. Complete route/caller review and retirement or explicit bounds for retained compatibility endpoints; see docs/compatibility-read-retirement.md.
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

## Bounded SCR detail — API 0.18.16, 2026-10-04 (Asia/Shanghai)

Mode: Codex cloud. Developed from GitHub main `bc28abe5f5f8d7e73b6b75b3c923268e0e2e7281`.
SCR detail now reads a scalar parent summary plus independently bounded acceptance
criteria, Issue relations, change points and DVP plans. Selecting a point or plan
loads its items by exact owned UUID, rather than loading every nested test item.
Complete counts remain visible on beyond-end or failed child pages; each cursor and
selection preserves the others. Default Chinese and selectable English remain.
Parent metadata, raw business text, materials UUID and coverage links are preserved.

The required change_id binds each child request to the resolved SCR UUID. Point/plan
UUIDs must belong to that SCR. These pins select live identity, not a frozen Snapshot
or cross-request transaction. Scalar SQL counts and bounded rows avoid growing ORM
graphs/ID lists. Duplicate display numbers and multiple Issue relation types are
preserved. Missing referenced Issues/DVP items are excluded as in the legacy profile;
real cross-plan DVP assignments remain visible. Point assignment counts count bindings,
not distinct tests, executions or passing results. Legacy rich APIs remain compatible.

No migration or write-contract change; head `0018_asr_evidence_index`, 14 command
contracts and public read-only mode remain. ROADMAP stays 34/44 (77%), read ledger
16/17 (94%): group 17 is still partial. Next inspect SCR coverage, Issue detail/impact,
organization and manufacturing reads; then approved identity/session, controlled
submission/recovery/corrections and operations. CI PR #1 remains unmerged. Conditional
estimates (4–8 packages toward internal use, 12–20 toward production review) remain
unchanged until the remaining rich-read scope is decomposed.

## Bounded SCR coverage — API 0.18.17, 2026-10-04 (Asia/Shanghai)

Mode: Codex cloud. Developed from main `79e5f767d74c818d2642aee8408d47c5ec733717`.
SCR coverage now separates a fixed SQL summary/full counts from paged candidate
releases, gaps, criteria, points, distinct Issues and owned-plan test items. Selecting
a group UUID loads its exact summary and bounded assigned tests; selected criteria
also expose bounded formal assignment history and the existing preparation link.
No page downloads all nested test/assignment histories. Full parent counts persist
on beyond-end or failed pages, and unrelated cursors/selection remain independent.
Default Chinese and selectable English are retained. Candidate pages replace the
first-100 dropdown; direct exact UUID selection remains possible beyond any page.

Coverage preserves legacy semantics: Issues are distinct despite multiple relations;
valid tests belong to this SCR's plans, foreign/missing links are excluded and counted
as gaps, latest execution_no on the exact release/FROZEN Snapshot wins, any latest
FAIL/ERROR/CANCELLED yields FAILED, all assigned latest PASS yields PASSED, otherwise
PENDING. Unassigned/no-context/no-freeze remain distinct. Assignment percent retains
Python rounding and null for empty groups. Formal criterion records remain visible
even when their test references are excluded. Unicode whitespace matches Python
strip for blank acceptance text. SCR detail still shows real cross-plan assignments;
coverage intentionally excludes them, as it did before this migration.

Page pins require exact change_id plus release_id/snapshot_id UUID or literal none.
Historical frozen execution pins survive newer freezes. A previously missing freeze
that now exists rejects stale none context with 409 instead of silently substituting
evidence. Current SCR definitions/assignments remain live: these pins do not freeze
definitions, confer incorporation, authorize release, or grant write permission.
Legacy report/assignment APIs, all 14 command contracts and schema head
0018_asr_evidence_index remain. Public staging stays sample-only/read-only.

Progress remains ROADMAP 34/44 (77%) and read groups 16/17 (94%); broad group 17 is
still partial. Next Issue detail/impact (linked SCRs, candidates and judgment history),
then organization/manufacturing reads; approved identity/session, controlled
submission/recovery/corrections and operations follow. CI PR #1 is unmerged.
Conditional estimates remain 4–8 focused packages toward internal use and 12–20
total toward production review, pending decomposition/provider decisions.

## Bounded Issue detail and impact evidence — API 0.18.18, 2026-10-04

Mode: Codex cloud. Developed from main `a248b1ab79578a960260f2e14f0d1abb80b06c4b`.
Issue detail now has a scalar parent summary/full counts plus independent linked
SCR relation, candidate release and complete judgment-history pages. Exact impact
review has a scalar context/latest judgment summary and independent distinct frozen
component and linked DVP verification pages. Both default-Chinese/English pages
retain complete counts on beyond-end/failed child reads and preserve unrelated
cursors. Materials, release/customer/project/Snapshot/item UUID links and exact
impact-preparation targets remain. Historical judgment links select their recorded
Snapshot UUID instead of silently showing the newest freeze.

Candidate scope preserves the prior software-product relationship via linked SCRs;
it does not infer impact or require the SCR's customer/project scope. Directory rows
retain the legacy real-product metadata visibility rule, full actual-release deployment
and batch counts, newest FROZEN Snapshot and newest judgment for that exact Snapshot.
Multiple relation types remain separate records; candidate releases are not duplicated.
History retains exact formal records when optional release/Snapshot display metadata
is missing. Distinct component code/version pairs normalize null versions to empty
strings. Verification includes real Issue-linked items across plans, selects latest
execution_no only for the exact release/Snapshot, and excludes missing DVP references.
A PASS is execution evidence, not an impact decision. Current Issue links and newest
judgments remain live; historical pins freeze execution selection, not definitions.

Required page issue_id binds the business number to the exact Issue UUID. Impact
pages additionally pin release path and Snapshot UUID/none. A historical FROZEN
UUID remains valid after newer freezes; stale none that now has a freeze returns
409. No migration, command contract/provider/grant changes; head
0018_asr_evidence_index and 14 commands remain. Public staging stays sample-only
read-only. Legacy rich APIs remain for compatibility.

ROADMAP remains 34/44 (77%) and read groups 16/17 (94%). Group 17 is still partial:
SCR/Issue detail/coverage/impact consumers are migrated, organization and manufacturing
catalogs/profiles remain. Next bound those reads, then approved identity/session,
controlled submission/recovery/correction/revocation and operational acceptance.
CI PR #1 remains unmerged. Conditional estimates remain 4–8 focused packages toward
internal use, 12–20 toward production review pending remaining scope/provider decisions.


## Bounded organization directories and profiles — API 0.18.19, 2026-10-04

Mode: Codex cloud. Developed from verified GitHub main `b3a621975d174d79444bf360ad978eec353ef30b`.
All six supplier/customer/project directory/profile consumers now use
`organization_views.py`, `organization-catalog.tsx` and `organization-profile.tsx`.
Directories fetch bounded scalar rows and full filtered counts instead of every
software/project/site name and release array. Open a profile to browse related
records. Profiles retain exact metadata/materials UUID, supplier introduction,
customer region/release-history link and project customer/platform/latest release.
Software portfolio, customer projects/current software and project sites each have
owned bounded pages. Project site links use the stored unique site code accepted by the existing
manufacturing profile route; the API retains each exact site UUID. Supplier
product links select its exact software UUID; latest
SSR and ASR links target the stored release UUID, not a version string.

Search treats wildcard characters literally; status/country/customer UUID filters
are exact. Region includes null-only UNASSIGNED; blank region selects all. Limits
are 1..100 (default 50), offsets 0..100000; unknown/kind-inappropriate fields fail
422. Stable code/UUID ordering avoids duplicate display-code pagination. Project
UUID selection retains precedence over code; duplicate codes return 409 and
canonical/uppercase/compact UUID links select the same project. Required
organization_id pins each collection to the resolved parent; a foreign pin is 404.
No parent or child rich-array fallback is used. Failed/beyond-end child pages keep
full parent counts; missing optional customer display metadata retains project UUID.

Counts preserve existing relationships: supplier products by supplier UUID;
customer projects by stored customer UUID; projects with current software require
real Release/detail membership matching both project and customer. Project latest
release uses detail project UUID alone, preserving legacy scope even when detail
customer differs. Supplier latest selects STANDARD releases only. Latest is
created_at DESC NULLS LAST then release UUID DESC. These are live context/count
observations, not release approval, impact, frozen evidence or access grants.

No migration, head `0018_asr_evidence_index`; all 14 write contracts unchanged.
Public staging stays sample-only/read-only, default Chinese/selectable English.
Legacy organization APIs remain compatible. Release matrix already has bounded
reads and is unchanged. The remaining group-17 consumers are manufacturing site
directory/detail and their line/current-deployment context; organization reads
are migrated. ROADMAP stays **34/44 (77%)**, read groups **16/17 (94%)**;
Phase 4 remains 8/9 until the entire open read acceptance item is verified.
Next manufacturing reads, then approved identity/session, controlled submission,
uncertain-result recovery/correction/revocation and operational acceptance.
CI PR #1 remains open/unmerged. Conditional estimates remain 4–8 focused packages
toward internal use and 12–20 toward production review, pending provider decisions.

Validation: full Python 3.12 backend **1048 passed**, **8687 warnings**, no skips,
including **125 real PostgreSQL 16.15 tests** on disposable migrated schemas.
23 new backend cases cover legacy parent/child/latest parity, exact cross-customer
release semantics, 205-parent and 120-child growth with constant scalar SQL/no ORM
identity graph, literal filters/null region, duplicate project-code identity,
missing metadata, owned pins and public-write rejection. PostgreSQL verifies
complete totals beyond 200, deterministic latest release ties and read audit purity.
Frontend **435 passed**, no skips; final Next/OpenNext production build passed.
**24 actual production Next SSR groups** verify six Chinese/English views, full
beyond-end totals, invalid owned pages, repeated catalog filters, exact related/
materials/release links and missing/foreign parents stopping child reads.
Single Alembic head/full upgrade SQL generation pass. Cloud rollout pending
at this feature commit; verified rollout will be recorded separately.


## Bounded manufacturing consumers — API 0.18.20, 2026-10-04

Mode: Codex cloud. Developed from verified main `4fc79aa4e04885465cc15a582cee101f235bc670`.
Manufacturing site directory now uses a scalar catalog with full filtered totals;
site detail uses a scalar summary and one owned bounded line page. Neither consumer
loads all sites, all lines or every latest-deployment changeover/batch history.
Stored metadata, full line/deployed/MATCH/attention/approved-authorization counts,
first-line context, recorded batch context and precise line command targets remain.
Detailed deployment history opens the existing bounded deployment profile/catalog.
Default Chinese/selectable English, independent failed/empty page states and full
parent counts remain. Directory now links exact site UUID; existing site-code links
from projects/production still work through the new resolver.

Latest deployment is per-line created_at DESC NULLS LAST then deployment UUID DESC.
MATCH/attention counts preserve stored deployment status, not rederived actual UUID
matches. Approved authorization counts use real current authorization status on
latest deployments; they count lines, not unique authorizations. No deployment is
not an attention state. All-MATCH requires at least one line. Summary first context
uses line name/UUID ordering. Recorded batch remains the earliest started_at/UUID
batch on the first name/UUID-ordered line with batches on its latest deployment,
regardless of batch status; it is not a claim of active production. Changeover
context is earliest changed_at/UUID on the first line's latest deployment. Null
history times sort last, matching production PostgreSQL ASC behavior. A new latest
deployment can remove an older batch/changeover context. Foreign-site/older-deployment
history cannot leak into these selections. Optional metadata remains null while
stored UUIDs survive. No arbitrary release/version substitute is shown.

New summary accepts exact site code or UUID (LIMIT 2); a UUID/code collision is
409, missing site 404. Required site_id binds each line request to its resolved
parent UUID; wrong pin is 404. Catalog supports literal q and exact status/region/
customer_id/project_id filters; limit 1..100/default 50, offset 0..100000/default 0,
extra/invalid fields 422. Stable site name/UUID and line name/UUID ordering.
Encoded site-code separators are supported by suffix path routes. Links preserve
actual existing route contracts: deployment/authorization/batch use stored unique
numbers; release uses UUID and type; Snapshot uses number plus manifest_snapshot_id
UUID; line expectation preparation carries exact line UUID. No bulk fallback.

No migration; head `0018_asr_evidence_index`; all 14 write contracts unchanged.
Public staging stays sample-only/read-only. Identified read-consumer ledger now
**17/17 (100%)**, previously 16/17: group 17's final two consumers are migrated.
This is consumer completion, not removal of compatibility APIs. ROADMAP remains
**34/44 (77%)**, Phase 4 **8/9 (89%)**: its literal remaining acceptance item asks
to retire or bound old compatibility reads after migration. Those endpoints still
exist with rich arrays; caller review and retirement/bounds are unfinished. The
criterion and denominator are not rewritten to claim earned completion. See
`docs/compatibility-read-retirement.md` for the concrete follow-up inventory.
Next complete that compatibility contract review, then approved identity/session,
controlled submission/outcome recovery, broader corrections/revocations and operations.
CI PR #1 remains open/unmerged. Conditional package ranges stay 4–8 internal-use /
12–20 production-review pending remaining contract/provider scope; no automatic reduction.

Validation: full Python 3.12 backend **1069 passed**, **9112 warnings**, no skips,
including **126 real PostgreSQL 16.15 tests** on disposable migrated schemas.
21 new backend cases cover legacy counts/latest/context parity, complete bounded
line windows, tied latest UUID selection, exact filters/pins, empty/foreign context,
missing metadata, encoded site code and ambiguous identifier, read-only denial and
120-site/line/deployment growth with constant SQL shapes and no ORM identity graph.
PostgreSQL verifies 209-line totals, latest MISMATCH precedence, missing current batch
and no audit writes. Frontend **448 passed**, no skips; production Next/OpenNext
build passed. **9 actual production Next SSR groups** verify catalog/profile zh/en,
full beyond-end context, failed/repeated pagination, empty-site CHECK, parent identity
stopping child reads and exact supported links/preparation UUID. Single Alembic head
and full PostgreSQL upgrade SQL generation pass. Cloud rollout pending at feature
commit; successful live verification is recorded separately afterward.

## Current continuation plan — API 0.18.21

First eight reviewed organization/manufacturing compatibility GET routes return 410
with bounded successors and no database graph loading. Remaining families still
prevent the Phase 4 checkbox from completion: progress stays 34/44, read consumers
17/17. See `docs/development-plan.md` for the current ordered packages, acceptance
criteria, external identity/environment dependencies and conditional estimates.

## Completion gate clarification — API 0.18.22

The seven groups in docs/development-plan.md are work groups, not seven turns.
Current version completion means all acceptance criteria and all 44 roadmap items
are implemented/verified; production release still requires company acceptance of
the actual target environment, security/permissions and recovery/data/network review.
Additional VIN/features and post-release maintenance are separate future scope.
Cumulative 19 reviewed compatibility GET tombstones do not close the remaining
Phase 4 item: overall stays 34/44.
