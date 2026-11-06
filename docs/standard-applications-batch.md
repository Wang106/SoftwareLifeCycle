# Standard catalog application batch read

## Scope and baseline

Candidate based on main `041a11d0fb7eedca04a4d6b2c8ed63f72e9df0af` (PR184).
That main's CI42221779232 completed successfully: 2112 frontend tests,
2861 backend tests plus 64 subtests, 296 PostgreSQL tests, and the unchanged
8 Next / 16 component strict browser journeys. Cloudflare production build
succeeded. Render's expired-database startup failure remains unresolved by
this package; the old database is not retained or rebuilt.

The existing standard catalog SSR requested one catalog and one applications
page for each row, in sequential batches of four. A default page of 50 rows
therefore required 51 HTTP reads before rendering. This package replaces that
fan-out with one bounded companion read, without a browser proxy, client-side
fetching, additional concurrency, authentication changes, or shared API timeout
changes. Native details, multiple simultaneous disclosures, default collapse,
filters, ordering, pagination links and failure-versus-empty presentation remain.

## Contract

The companion GET endpoint derives parent IDs from the same catalog filters
and current page, rather than accepting arbitrary parent ID lists. Catalog
limit remains at most 100 and offset at most 100000. Each parent returns at
most 10 children. Only the selected in-page parent uses the requested child
offset; all other parents start at zero. Returned application fields remain
id, version and status plus existing pagination metadata. No additional
customer, project, notes, source or identity information is projected.

The target is at most two sequential HTTP reads and five SQL statements for
a nonempty rendered catalog: two existing catalog statements and three batch
statements (parent page, grouped totals, partitioned child page). An empty
catalog does not require a companion HTTP read. The batch response has a
2 MiB serialized limit and at most 1000 children. Over-limit responses fail
explicitly, never truncate into a misleading successful result.

Counts remain exact and ordering stays creation time descending, nulls last,
then ID descending. Existing stored associations are preserved; missing child
Release records remain excluded. Query/result count bounds do not establish
a bound on database scanning or sorting time. PostgreSQL plans and representative
synthetic workloads must be checked before claiming a database latency gain.

Two separate reads can observe concurrent catalog changes. The frontend must
match envelopes to the originally displayed parent and expected child page;
missing or mismatched batch envelopes fail closed, never assigned to another row.
Invalid selected child pagination leaves only that selected row unavailable;
the other rows still receive their first pages. Direct duplicate query values
retain the existing FastAPI last-value semantics; frontend duplicate search
values retain the existing invalid-value handling. The new batch success and
size-limit failure responses explicitly use Cache-Control: no-store.
A failed batch retains the directory and reports unavailable child pages.
There is no per-row fallback, cross-user cache or service configuration change.

## Validation status

Frontend final validation: 2116 tests passed, with no failures or skips;
18 focused tests, TypeScript, configuration, browser-auth checks and the
Next/OpenNext Cloudflare production build passed. The initial production
build was blocked by an external node_modules symlink; copying the existing
dependencies locally resolved that workspace-only issue without changing
dependencies or configuration.

Final-tree backend full run: 2055 passed, 64 subtests passed, and 824 tests
skipped because TEST_POSTGRES_URL is absent (821 PostgreSQL/locking-related
cases and three native backup/restore cases), in 260.58 seconds. This is not
a strict PostgreSQL CI pass. Backend focused validation: 32 passed, two
PostgreSQL tests skipped locally.
The new batch test alone includes a migrated PostgreSQL plan test with 101
parents, 12 children each, and 5001 additional children for both an in-page
and an off-page parent. It records actual EXPLAIN ANALYZE BUFFERS JSON plans
in JUnit properties and checks real NULL timestamp ordering. This has not
run locally and is not yet latency or query-plan evidence.

52 automation and 126 gate-guard tests passed; browser discovery retained
8 Next and 16 component cases. Local PostgreSQL
and the fixed signed macOS browser are unavailable; their checks require the
existing CI environments. No candidate CI or production performance result is
claimed here. Independent final review found no blocking issue. Candidate exact-head CI
and PostgreSQL plans remain pending publication. No new index or migration is included without separate review.

This optimization does not restore the unavailable public backend, establish
cold-start FCP/TTFB improvements, or complete offline deployment. Business
acceptance remains 36/44 (82%), delta zero, browser stage 1/4 and finite plan 8/8.
