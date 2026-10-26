# Batch and Changeover correction history: public sample read

## Missing user capability

Baseline main `26abe923683885bf10add3121546381a921f3cac` closes the nested correction
write-authorization mismatch (PR153), but users could still only see effective Batch
facts or a Changeover catalog. The Batch page did not show original facts, correction
reasons or audit references. Neither child exposed the revision/head pair required
by the existing correction commands. This package adds a real read-only history view,
not another submission endpoint or a production-acceptance claim.

Maps to R12 and Phase6's append-only correction/trace work. Full correction E2E and
real identity/browser/multi-user acceptance remain open; progress stays36/44=82%.

## Routes and projection

GET `/api/v1/deployments/{deployment_no}/batches/{batch_no}/history`

GET `/api/v1/deployments/{deployment_no}/changeovers/{changeover_no}/history`

Both exact business numbers must match the same parent-child relation. Missing or
mismatched targets return the same404 and fixed `production history target not found`.
This is **parent binding, not principal authorization**. Existing production reads
and server `apiGet` are public sample reads; this package preserves that contract.
It does not enable real/company data exposure, add a private read transport, provision
identity, grant permissions or change public read-only/OIDC settings. A protected
real-data history service requires separate authorization and target acceptance.

One SQL statement captures the child, baseline, newest50 corrections and windowed
total count. Effective values, revision and head ID derive from that same result,
not a later effective-state query. A concurrent appended correction cannot create
a mixed old-value/new-head response. No GET locks or writes are used. Label metadata
is separately loaded in bounded set queries (at most4 queries total); these labels
are not a cross-table historical snapshot. A Batch's linked Changeover label is
resolved only within the exact parent. No actor identity, principal ID, request JSON,
token, headers or arbitrary audit payload is selected or returned.

The response distinguishes:

- Stored status: observed physical status, not new permission or derived approval.
- Recorded baseline: original captured values and source (`LEGACY_CURRENT`,
  `IMPORTED_CURRENT`, `FIRST_RECORD`), recorded time and optional original audit ref.
- Effective recorded facts: current replacement values, revision and head ID.
- Corrections: newest-first revision, predecessor, full replacement facts, reason,
  ledger time and exact audit event reference; total count and truncation are explicit.

No baseline remains `NOT_RECORDED`; legacy physical values are shown as current
stored observations, never invented as an audited baseline. A null corrected field
replaces the prior value instead of silently falling back. A bounded view does not
delete older rows. History is an observation that can become stale; it is not proof
that a submitted request succeeded, a replay receipt, or evidence of physical flashing
or rollback. No new browser write or recovery controller is added.

## User-facing view

Nested pages `/deployments/{deployment}/batches/{batch}/history` and
`/deployments/{deployment}/changeovers/{changeover}/history` are discoverable from
both production catalogs; Batch detail also links with its resolved parent.
They show original versus effective facts, baseline provenance, latest corrections,
revision/head/predecessor, reasons and audit trace links. Labels and known state
codes are bilingual; raw business evidence is escaped and remains untranslated.
Missing/mismatched/malformed basic response structures render unavailable rather
than substitute data. No form, request key, write control or automatic retry exists.

## Validation and limitations

34 new backend cases:16SQLite and18realPG variants, including two deterministic
concurrent-append-during-metadata tests. Coverage includes no baseline, each baseline
source, null replacement, effective projection parity, parent mismatch/absence,
public GET while writes remain blocked in read-only mode, identity/payload exclusion,
and56-record growth with only50 returned and bounded queries. Concurrent tests append
a real second correction after the first projection query and verify a coherent old
response followed by a coherent fresh response; they require real PostgreSQL in CI.

21 new frontend render tests cover both languages, routes/links, bounded latest-first
history, missing provenance, escaped evidence, malformed/mismatched response refusal
and absence of write controls. They are SSR tests, not actual browser/operator or
provider-backed acceptance. A reviewer attempted an isolated local static-fixture Chromium render; browser startup failed at sandbox socket permission. No bypass/retry was attempted; visual/browser acceptance remains unverified.

Initial new backend tests incorrectly expected `LEGACY_CORRECTED`; existing service
bootstraps an imported current-value baseline. Work paused, and user explicitly
approved correcting those two parametrized expectations to `IMPORTED_CORRECTED`.
No service behavior, existing test or gate changed to make them pass.
The first complete frontend run then reported1597pass/1failure: the new component
lacked the existing i18n structural wrappers. Work paused again; user explicitly
approved adding three root `Localized` wrappers. They do not recursively translate
nested React elements, so raw business evidence remains unchanged. Existing gates
and tests were preserved and the complete suite was rerun. Dependency
installation initially hit an unwritable default npm cache; existing lockfile install
succeeded with `/tmp` cache, without permission or dependency changes.

Exact-head full unchanged CI, independent review, protected merge, fresh main CI and
separate Cloudflare/Render evidence remain mandatory; final results are recorded in
the PR. No synthetic or code-only result completes real private history acceptance.

## Next missing capability

A separately scoped controlled Batch/Changeover correction preparation/confirmation
and submission/recovery experience can consume this coherent head context. It must
retain exact parent authorization, stale-version conflicts, immutable request retries,
original audit receipts and default-off/public-read-only boundaries. This package
does not count either correction command as an accepted real user workflow.
