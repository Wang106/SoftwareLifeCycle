# Read-consumer migration tracking

Reviewed main baseline: 665c0335d278125b748a4aa05e16ea0a5e60d9e2.
Updated 2026-10-03 (Asia/Shanghai), API 0.18.15.

The top-level ROADMAP counts completed acceptance items: 34/44 (77%). The remaining
Phase 4 item covers several consumers, so finishing one consumer does not complete
that entire item. This new ledger tracks **17 named scope groups**, equally counted
for visibility, not weighted effort or production readiness. At the original 27ce7b7 baseline,
11/17 groups were migrated; exact detail made 12/17 (71%) at 2f34a9a. Comparison made 13/17 (76%); passport made 14/17 (82%); readiness
made 15/17 (88%); release catalogs/resolver now make 16/17 (94%) under the same scope grouping. This is a finer
breakdown, not a replacement for ROADMAP's denominator. A group closes only
when its identified frontend consumer no longer relies on the bulk read. Legacy
compatibility APIs can still exist; removing them requires caller review.

| # | Consumer scope group | State | Code evidence / remaining work |
| --- | --- | --- | --- |
| 1 | Deployment detail | Migrated | backend/app/api/production_catalog.py; profile/counts and bounded provenance/history |
| 2 | Authorization detail | Migrated | backend/app/api/distribution_catalog.py; bounded profile and delivery reads |
| 3 | Distribution detail | Migrated | backend/app/api/distribution_catalog.py; profile and catalog history |
| 4 | Exact Delivery revision | Migrated | backend/app/api/distribution_catalog.py; exact revision artifacts and history |
| 5 | ASR downstream | Migrated | backend/app/api/dashboard.py; summary and authorization-release-scoped catalogs |
| 6 | ASR evidence | Migrated | backend/app/api/asr_evidence.py; pinned Snapshot artifact/execution pages |
| 7 | Shared release coverage | Migrated | backend/app/services/change_coverage.py; SQL counts for shared release consumers |
| 8 | SSR details | Migrated | backend/app/api/standard_release_views.py; summary, components and baseline users |
| 9 | ASR component declarations | Migrated | backend/app/api/asr_components.py; declarations/unlinked baseline pages |
| 10 | ASR frozen policy | Migrated | backend/app/api/asr_policy.py; pinned metadata/rule pages |
| 11 | Snapshot history | Already bounded | backend/app/api/releases.py; limit/before_number cursor pages |
| 12 | Exact Snapshot detail | Migrated | backend/app/api/snapshot_views.py; summary and independently bounded manifest/rules; search selects exact file |
| 13 | Snapshot comparison | Migrated | backend/app/api/snapshot_comparison_views.py; SQL summary and pinned bounded differences, exact rule-inspection links; legacy API remains |
| 14 | ASR passport | Migrated | backend/app/api/asr_passport.py; fixed summary and four independently bounded histories, paired UUID pins and safe historical release display |
| 15 | ASR readiness and compatibility policy reads | Migrated this package | backend/app/api/asr_readiness.py; SQL coverage/policy/exception aggregates and bounded approved exceptions; eight gates unchanged. Legacy array APIs/evaluate retained, not retired |
| 16 | Release catalogs and legacy resolver | Migrated | backend/app/api/release_catalog.py; both release directories use bounded pages/full counts; legacy-release.ts uses exact bounded UUID/version resolution, including ambiguity beyond 200 rows |
| 17 | Other rich profiles and legacy domain catalogs | Partial | SCR/Issue directory pages now use backend/app/api/change_catalog.py and complete SQL counts. SCR detail now uses backend/app/api/change_views.py and independently bounded collections/selected-child items. SCR coverage now uses backend/app/api/change_coverage_views.py with full SQL summary, independently bounded collections and exact selected-group items/assignment history. Issue detail/impact now uses backend/app/api/issue_views.py for full-count relation/candidate/judgment pages and Snapshot-pinned component/verification pages. Organization catalogs/profiles and manufacturing catalogs/profiles remain. This broad group is not complete |

Groups 16–17 are broad and can require several packages. Splitting a group later must
record a denominator change rather than implying earned progress. New consumers must
be added explicitly. The generic /releases/[id]/passport and readiness pages redirect
to ASR via the legacy resolver; no independent SSR passport migration is claimed.
No approved OIDC environment, authenticated UI submission, broad correction/revocation
or operational release acceptance is inferred from this read work.

Next: remaining rich profiles/domain catalogs (group 17); then
approved identity/session, controlled submission and recovery/corrections, operations.
Planning ranges remain conditional: 4–8 focused packages toward internal use and
12–20 total toward production review, subject to remaining group sizes and provider
configuration. Public staging remains read-only throughout.

### Group 17 directory slice — API 0.18.15

Completed this package: frontend `/changes` and `/issues` stop loading bulk lists.
Two directories are migrated; rich profiles/domain catalogs remain. No denominator
change, no earned group completion: 16/17 (94%), ROADMAP 34/44 (77%).
Next bounded SCR detail collections, then Issue detail/impact and organization/
manufacturing reads. Existing estimates remain conditional, not automatically reduced.

### Group 17 SCR detail slice — API 0.18.16

SCR detail parent and selected point/plan item consumers migrated. This adds no scope
group completion: 16/17 (94%), ROADMAP 34/44 (77%). SCR coverage, Issue detail/impact
and organization/manufacturing reads remain to inspect/migrate. Identity/session,
controlled submission/recovery/corrections and operations remain. Public staging
is sample-only read-only; package estimates stay conditional and unchanged.

### Group 17 SCR coverage slice — API 0.18.17

Summary, candidates, gaps, definitions, owned-plan items and selected-group
evidence/criterion history migrated. Group 17 remains partial: 16/17 (94%),
ROADMAP 34/44 (77%). Next Issue detail/impact, organization/manufacturing reads.
Current definitions are not frozen by historical execution context pins. Legacy
report remains compatible; public writes stay denied. Estimates unchanged.

### Group 17 Issue detail/impact slice — API 0.18.18

Issue parent, linked SCR relations, candidates, full judgment history and exact
impact component/verification consumers migrated. Group 17 remains partial:
16/17 (94%), ROADMAP 34/44 (77%). Next organization and manufacturing reads;
then identity/session, controlled submission/recovery/corrections and operations.
Historical execution pins do not freeze Issue links/judgments. Estimates unchanged.
