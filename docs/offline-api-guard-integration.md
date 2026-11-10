# Guard comparison around migrated API requests

## Verified baseline

PR215 is merged as main `952299eef8b242cd0cd3082d7bf7cc69aae8fe4a`.
[Main CI42805706655](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42805706655)
passed: 3647 backend tests, 2881 subtests, 308 PostgreSQL-module cases without skips,
2274 frontend tests, strict 16+16 browser journeys and the 0029 migration checks.
Cloudflare production build `ae92a73f-db2b-4bcb-bd42-8ac2f8208f0f`, version
`53b89a1b-9f99-41f2-8645-f69cfc7e24ea`, succeeded. Actions deployment/continuation
were skipped; Render was not checked. Earlier unpublished PR215 records are historical.

The separately approved actual [joint run42798938628](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42798938628)
succeeded at the earlier main `86e3fba3d3f8c5b5334ecb1cfd683b952272195b`.
It verified limited counts and five API cases and confirmed removal of two preparation
plus three joint containers. It did not execute the PR215 comparator or this integration.

## Bounded integration

This package connects the existing collector and fixed nine-contract comparison to
only the opted-in migrated API lifecycle. Existing migration-only operation remains
unchanged. No new CLI, workflow input, target URL, SQL option or automatic execution
is added. The existing manual workflow still defaults off.

A trusted coordinator verifies the exact requested commit, canonical host modules and
unchanged fixed manifest. The collector bytes that passed verification are carried
forward in a bounded Python program; they are not reread after verification. The helper
uses the existing API image's Python/psycopg in its already-owned running container.
There is no additional container, image context, Dockerfile, dependency, role or grant.
These checks establish consistency under a reviewed checkout and trusted local daemon,
not provenance authentication or an authorization capability.

The sequence is:

1. Existing same-run preparations, owned empty PG migration and limited count checks.
2. Start/validate the existing API, then verify same PG custody, process and network.
3. Collect and require all three function and six trigger contracts to match.
4. Execute the same five HTTP checks, with their existing bounds and expected results.
5. Collect and compare once more; require the same namespace OID and PG version.
6. Validate the API process, remove the API, run the existing post-removal count checks,
   then remove the migration container and PG through the original owned-CID cleanup.

This is **request-bracketing comparison while the API is alive**. It is not a comparison
before API startup or after API removal, and two observations do not prove continuous
invariance between them. The post-removal check remains the original limited counts.

## Connection and private transport

The bootstrap accepts only the coordinator's expected network identity. It checks the
non-root process and loopback-only network. The database target is fixed to
127.0.0.1:5432/slc_migration, user postgres, namespace public. It never parses the app's
DATABASE_URL or accepts an external target. Expected PG environment is checked;
unexpected PG overrides cannot select another host, service or credentials file.

The connection has a five-second timeout. It explicitly starts a read-only repeatable-read
transaction, sets search_path to pg_catalog and bounded statement/lock/idle timeouts,
and invokes the unchanged collector. No DDL, role/ACL operation or app business query is
added. Rollback and connection close must both finish before a success envelope is sent.
The inner collector retains transaction_completed=false; the separate runner envelope
records only the completion observed by this invocation.

Catalog IPC has a distinct 512 KiB cap for the entire serialized envelope. It does not
widen the existing 4 KiB HTTP execution or 64 KiB generic JSON limits. Oversize, duplicate
keys, invalid UTF-8, nonfinite/float values, unexpected fields and incomplete completion
markers fail closed. Host comparison requires all nine exact checks, not only a success
label or count. The fixed namespace is preserved, never relabeled for the 120-fact checker.

Raw definitions may contain trigger argument/WHEN text. They remain in bounded in-memory
process pipes and are not logged, persisted, attached or placed in the final receipt.
Failures expose fixed codes rather than database text or rejected values. The final v2
probe/lifecycle receipts contain only fixed coverage, the two nine-check summaries and
the number of completed collection transactions.

## Budgets, cleanup and limitations

The original 55-minute deadline is never refreshed. New source checks reserve existing
downstream work. Both collections fit inside the existing 120-second API work window;
a per-call cap is not an extension of that window. Existing API cleanup and post-count
phase bounds, outer cleanup and final reserve remain. Exhaustion can reject an otherwise
valid run; it does not authorize retry, timeout extension or weaker checks.

A pre-check failure skips HTTP; a post-check failure prevents success. Neither retries
collection. Existing first-error priority, control exceptions and one-attempt exact-CID
cleanup remain mandatory. Lost runners or CLI/daemon uncertainty can leave resources;
receipts cannot guarantee cleanup after host loss.

Temporary superuser trust and read-only transactions are not SELECT-only privileges.
readonly_role_verified, complete_schema_verified and provenance_authenticated remain
false. This does not prove all schema attributes, function behavior, all business rows,
real identity, physical network isolation, restore, offline transfer or company deployment.

## Validation and execution boundary

Initial 12 integration and 19 helper capability tests failed before implementation.
Additional red regressions cover escaped program size and work-Budget mutation blocking
API cleanup. After the specific cleanup correction notice/pause, the API uses a separate
original-deadline cleanup adapter; work still rejects deadline changes. Local tests mock acquisition, Docker, network, API, database and psycopg operations.
Existing regression tests can execute bounded local Python subprocesses and fixture reads. Program
contracts execute the actual bootstrap only with fake connections and network/process
metadata. They do not start a service or run SQL. Existing full CI remains unchanged;
its existing owned PostgreSQL cases are separate evidence from manual image execution.

No manual rehearsal is triggered by this package. Any later execution must use the
explicitly authorized workflow and be verified as a new exact-commit run; historical
runtime results cannot be carried forward as this integration's runtime acceptance.

13 integration, 29 helper, 27 existing API probe and 20 lifecycle methods pass.
826 full offline, 52 automation and 126 CI guard tests pass, along with compilation,
progress and whitespace checks. Independent final review passed 188 focused/adjacent tests
and 3,825 additional adversarial checks with no blocker. Its documentation precision note
was corrected. Exact-candidate CI remains pending; this is not actual image runtime evidence.

Business 36/44=82%, increment0; modules100/100demo/100demo/100/89/60/17;
plans100/100/20/33/40/40/0; browser1/4 and finite plan8/8 unchanged.
