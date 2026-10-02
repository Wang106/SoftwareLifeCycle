# Read-consumer migration tracking

Reviewed main feature baseline: 8ab38722f62b7221fe8cdf90e9c3c70cb07d935d (translation follow-up 03892f7637e92a2f402118c0d4dcfb351baaf838).
Updated 2026-10-03 (Asia/Shanghai), API 0.18.12.

The top-level ROADMAP counts completed acceptance items: 34/44 (77%). The remaining
Phase 4 item covers several consumers, so finishing one consumer does not complete
that entire item. This new ledger tracks **17 named scope groups**, equally counted
for visibility, not weighted effort or production readiness. At the original 27ce7b7 baseline,
11/17 groups were migrated; exact detail made 12/17 (71%) at 2f34a9a. Comparison made 13/17 (76%); this package
closes passport, making 14/17 (82%) under the same scope grouping. This is a finer
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
| 14 | ASR passport | Migrated this package | backend/app/api/asr_passport.py; fixed summary and four independently bounded histories, paired UUID pins and safe historical release display |
| 15 | ASR readiness and compatibility policy reads | Pending | backend/app/api/dashboard.py and services/artifact_policy.py still read whole artifact/rule/execution sets; preserve readiness and write validation semantics |
| 16 | Release catalogs and legacy resolver | Pending | frontend release/application and release/standard catalog pages; frontend/lib/legacy-release.ts still loads application catalog for UUID/version resolution |
| 17 | Other rich profiles and legacy domain catalogs | Pending | frontend changes/issues/organizations/manufacturing catalogs and details; change coverage/issue impact child sets need individual review and bounded contracts |

Groups 15–17 are broad and can require several packages. Splitting a group later must
record a denominator change rather than implying earned progress. New consumers must
be added explicitly. The generic /releases/[id]/passport and readiness pages redirect
to ASR via the legacy resolver; no independent SSR passport migration is claimed.
No approved OIDC environment, authenticated UI submission, broad correction/revocation
or operational release acceptance is inferred from this read work.

Next: readiness/remaining catalogs and rich reads; then
approved identity/session, controlled submission and recovery/corrections, operations.
Planning ranges remain conditional: 6–10 focused packages toward internal use and
14–22 total toward production review, subject to remaining group sizes and provider
configuration. Public staging remains read-only throughout.
