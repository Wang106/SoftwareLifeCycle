# Internal same-run migration/API lifecycle

## Actual execution update — 2026-11-10

PR214 is merged as main `86e3fba3d3f8c5b5334ecb1cfd683b952272195b`.
[Main CI42794359157](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42794359157)
and Cloudflare production build `dc3a54b5-3f7b-4f68-abdd-c0fff808f3ba` succeeded.
Separately approved [joint run42798938628](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42798938628)
passed once (attempt1) at that commit: API started/ready, five checks passed,
original migration0029 and selected empty observations, 2 preparation + 3 joint
containers confirmed removed. No artifacts were uploaded. This is limited synthetic
runtime evidence, not full schema, least privilege, provenance or deployment.

The [new finite guard comparison](offline-pg-guard-contracts.md) is not wired into
this lifecycle; that earlier successful run cannot validate it. Development-time
unpublished/unexecuted statements below are historical checkpoints, not current
claims that the separately approved runtime never happened.

Current entrypoint update (2026-11-10): a separate default-off CLI/manual workflow
is prepared in [the entrypoint package](offline-migrated-api-rehearsal.md). The older
CLI/workflow remain migration-only. No new actual lifecycle operation was run.

## Current scope

PR212 is merged as main `c5fcf45cb6c8b1d7b9a49d845b8f5cc1e2951b08`.
Its [main CI42770999377](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42770999377)
passed, including 3589 backend tests, 2749 subtests and 308 PostgreSQL-module
cases without skips. That is baseline evidence, not execution of this new path.

This package connects existing API preparation/probe helpers through an internal
`run(commit, include_api=True)` path in the migration/database coordinator.
The keyword accepts only a real boolean and defaults to false. No CLI flag or
workflow option is added. Existing CLI and manual workflow stay migration-only.
Import/help do not acquire images, create containers or start an application.
No production source, Dockerfile, dependency, migration, CI gate or permission is
changed. Development uses only synthetic files and mocked daemon/HTTP/DB calls.

A future trusted caller must receive specific approval for actual acquisition,
builds, owned containers, shared network namespace, temporary superuser trust,
empty-database DDL, API startup/read-only probes and exact-CID cleanup. It must
install SIGTERM handling before invocation, like the existing CLI wrapper. This
internal option and its receipts do not grant approval. No real operation has
been executed for this package, and no future CLI/workflow is implied as approved.

## Lifecycle and evidence

1. Bind the coordinator, preparation, probe, startup and transitive helper module
   locations and source bytes to the requested commit. Existing builders also
   independently reject dirty, wrong-commit and unsafe source inputs.
2. Build the migration image using the existing builder and original start time.
   Prepare the API image in a separate fresh private child directory with the
   same coordinator Budget object, before any PG container exists. No old
   receipt, tag or previously retained image substitutes for this preparation.
3. Require the API preparation receipt's exact schema/types, commit, distinct
   image ID and valid context/build digests. Its application/database/provenance
   flags must remain false. Malformed evidence stops before PG creation.
4. Create the existing owned tmpfs-only PG, execute the original migration image,
   require successful exit and the existing finite schema/count observation.
   Failures skip API entirely and retain the existing owned cleanup path.
5. Pass the live PG object, exact netns, same-run API ID/commit, original Budget
   and outer local-daemon adapter to the existing API probe. Do not pass the
   expired migration-stage command closure. The helper validates custody/PID/
   network consistency and performs its five fixed checks: ready200, two empty
   read catalogs, business403 and identity401. It removes only its own API,
   then verifies the selected PG observation again.
6. Validate the exact probe receipt, including five integer cases, both exact
   observations, true readiness/API removal and false role/full-schema/provenance
   claims. Outer finally attempts migration then PG removal, once per known CID.
   No name search, prune, export, upload or automatic retry is added.

Only complete success produces the new lifecycle receipt. It separately reports
2 preparation containers and 3 joint containers removed. The default migration
receipt remains unchanged. Receipts are trusted-run consistency, not signed
provenance, complete schema validation, least privilege or deployment acceptance.
Default read-only PostgreSQL sessions under temporary postgres superuser trust
are not a SELECT-only role. No company/old database, real identity or writes are
approved through this package.

## Time and failure boundaries

The original 55-minute start is never refreshed. Before host/PG acquisition the
API path requires 1330 seconds plus the common 30-second final reserve. PG pull
reserves 730; PG creation requires 730+30. The migration stage is capped at 300
seconds and at original deadline−460, reserving 430+30 through its work adapter.
The API helper keeps its own 120/40/30-second stages and 330-second entry floor.
Its outer adapter reserves 100+30, leaving the existing 90-second outer cleanup
and 30-second final margin. These are upper bounds and admission floors, not a
promise that preparation can fit the total window.

API preparation retains its separately reviewed 630-second reserve. The stronger
1330-second downstream gate can therefore reject after an expensive preparation
has completed; no PG is created in that case. This package deliberately does not
alter or extend the helper, builder or total budget to disguise that limitation.

The opted-in outer cleanup deadline is anchored to the captured original deadline,
not a mutable Budget field. Budget mutation rejects the operation and cannot grant
cleanup more time or suppress still-available cleanup. If that original time is
already exhausted, cleanup remains uncertain rather than exceeding the deadline.
The first work exception keeps priority. If no work exception exists, the first
KeyboardInterrupt/SystemExit during cleanup is preserved and rethrown after
remaining owned cleanup attempts. Ordinary cleanup failures remain fail-closed.
An API removal failure does not prevent attempts to remove migration then PG.

SIGKILL, repeated interruption, host loss or daemon-side uncertainty can still
leave resources. CLI termination is not evidence that daemon work stopped.
Private custody/context evidence remains for diagnosis; no broad cleanup or retry.

## Verification and remaining work

The initial 14-test capability suite failed before implementation. A failing
cleanup-control contract preceded its targeted repair. Independent review then
reproduced cleanup using a mutated deadline; a failing near-deadline regression
preceded the fix to the captured deadline. Final tests cover forward/backward/
invalid mutation, exact receipts, missing fields, boolean/integer aliases,
transitive sources, default false/CLI rejection, original live budget, migration
stage expiry, skipped probe after failed migration/observation, and cleanup order.
All acquisition/Docker/HTTP/PG execution is mocked; no application listens.

Local focused 20 contracts pass via discovery and direct execution. Full offline,
automation, CI guard, compilation, progress and diff evidence is recorded in the
current checkpoint. Exact-candidate CI, frontend/real PostgreSQL/browser gates,
and any real lifecycle runtime must be reported separately. No actual runtime is
accepted by these local checks. The later reviewed entrypoint and approved actual run are recorded above;
the new finite guard comparison is not integrated.

Business 36/44=82%, increment 0; modules 100/100demo/100demo/100/89/60/17;
plans 100/100/20/33/40/40/0; browser stage 1/4, finite plan 8/8 unchanged.
