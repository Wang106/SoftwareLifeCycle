# Offline read-only image packaging and synthetic rehearsal design

Date: 2026-11-06 (UTC+8). Baseline main `e6e03b76f8e662652cf0ad321912eeac885ee9e1`.
This is a documentation-only design, not an installer, runnable bundle or permission
to configure a server. PR181 browser evidence is recorded in
[browser-authorization-b3-cancel-retry.md](browser-authorization-b3-cancel-retry.md).
Its8+16 journeys do not execute containers or establish offline readiness.

## Existing pieces and concrete gaps

The [configuration preflight](offline-readonly-config-preflight.md),
[validator](../scripts/offline_readonly_preflight.py) and
[tests](../backend/tests/test_offline_readonly_preflight.py) validate bounded
single-image docker-save archives and render localhost-only Compose JSON.
They do not load images, provision PostgreSQL, enforce host egress, or start services.
Synthetic tar fixtures are not runnable images. No Docker executable is available
in this development workspace; no runtime result is claimed.

Existing [API Dockerfile](../backend/Dockerfile) uses floating python:3.12-slim,
broad COPY and automatic migration/seed entrypoint. The
[web Dockerfile](../frontend/Dockerfile) uses floating node:22-alpine and copies the
whole build directory. Neither labels the source revision or proves the proposed
nonroot/read-only runtime. Existing ignore lists are not an audited artifact
allowlist. Do not use [development Compose](../docker-compose.yml) on the target.
These are gaps against the new offline profile, not claims of exploited flaws.

The selected candidate remains Windows Server2016 → Hyper-V → Ubuntu24.04 amd64
VM → Docker Engine/Compose>=2.30.0, subject to operator capacity/compatibility
approval. No VM, Docker, PostgreSQL or import process is installed or verified.
The personal Mac and company server are not build/test targets for this package.

## Proposed build acceptance, before a runnable bundle claim

1. Select an authorized disposable Linux/amd64 Docker build/test environment with
   existing capacity. If unavailable, report it; do not install software, change
   host security or buy resources silently. Build in a connected staging environment;
   importing and running on a disconnected target are separate stages.
2. Pin official base images by verified platform-specific digest and record source,
   immutable repository commit, lockfiles, builder/runtime versions and build logs.
   No invented digest or provenance. Existing pinned Python dependencies still need
   reproducible artifact/hash review; a version pin alone is not a verified wheel.
3. Use dedicated offline recipes and explicit source allowlists, not edits to the
   current deployment profile. Exclude .env files, credentials, operator bundles,
   local caches, tests/build reports and repository metadata. Review every image
   layer and final config for secrets and unexpected endpoints/settings; deleting
   a secret in a later layer does not remove it. Record dependency/license/security
   review. Checksums and revision labels bind bytes; they do not authenticate trust.
4. Both API/web must label the same exact source revision, linux/amd64 and immutable
   image ID. Prove executable/read permissions for UID/GID65532 and read-only root
   filesystem with bounded temporary storage. No baked runtime credentials/settings,
   image-declared VOLUME or unexpected config environment. Next build-time public
   variables require explicit inspection, not runtime clearing alone.
5. Export one uncompressed docker-save archive per service. Record size, SHA256,
   config/image ID, platform, revision, layer diff_ids and reviewed provenance.
   Exercise the existing preflight against real exports. Missing/mismatched bytes,
   links/traversal, unexpected metadata or revision mismatch must fail closed.
   Do not expand accepted archive formats merely to make a candidate pass.
6. Inventory the separately approved target prerequisites: OS/runtime packages,
   Docker/Compose versions, PostgreSQL packages/configuration, schema tooling,
   trusted checksums and transfer procedure. The two application archives alone
   are not a complete offline installer. Prove no implicit package fetch is needed
   during target load/start/health/browser checks.

## Proposed isolated runtime acceptance

Use only a disposable synthetic database and operator-managed ephemeral secrets,
never production credentials/data or the expired public database. Secret files stay
outside git/logs/CI artifacts. Database setup, role grants, image load/start and
host egress controls need their own applicable authorization before execution.

- Before startup, independently attest schema0029, synthetic dataset and a
  non-owner/non-superuser SELECT-only role without write/CREATE/TEMP privileges.
  Validate actual grants/role inheritance, not operator JSON booleans. Record a
  baseline schema/data digest. Setup writes belong to a separately authorized
  disposable setup phase, not application startup or runtime approval.
- Render and parse Compose with the supported version; reject build/pull behavior,
  missing local IDs and image mismatch. Verify the effective configuration retains
  all disabled identity/submission gates, no seed/migration entrypoint, loopback
  binds, nonroot identity, read-only root and original capability constraints.
- Prove actual process listeners on127.0.0.1:8000/3000, health/readiness and exact
  schema. Host network mode is not egress isolation. Test offline behavior under
  an explicitly approved isolated-host egress boundary, including denied external
  DNS/connections and no pull/download fallback. Do not change company firewalls.
- Exercise bilingual read-only pages and bounded unavailable/error states against
  the real synthetic API/database. Verify disabled mutation controls and denied
  write requests; in the disposable database, negative SQL permission probes must
  fail without changing data. Compare schema/data digest afterward and inspect
  logs for absence of startup migration/seed and secrets. Health alone is insufficient.
- Stop/restart the same immutable images and repeat acceptance with no new fetch;
  fail safely when images, schema or database are missing. Capture exact-source
  reports, effective redacted configuration, version evidence and residual limits.
  Cleaning up the disposable environment must not affect unrelated resources.

No pass is predeclared. Any permission, host/runtime incompatibility, unsafe image,
secret exposure or uncertain write outcome stops the affected action for review.
Do not weaken existing CI/browser/security gates or replace the signed Chrome.

## Package boundaries and next implementation

This seven-file package closes PR181 evidence and specifies acceptance only.
After its exact-head CI and protected merge/main verification, the next bounded
proposal is to verify available build infrastructure and immutable official source
inputs, then implement reviewed dedicated image recipes/packaging contracts. A
runtime CI job or host provisioning is a separate concrete scope, not implied here.
If build infrastructure is unavailable, report that blocker rather than labelling
static tests as runtime success or repeatedly adding browser mocks.

Even successful synthetic rehearsal would establish only localhost read-only
technical feasibility. Company installation/backup/rollback, offline transfer,
capacity, network/HTTPS, identity roles, real data, write workflows and operational
acceptance remain separate. No calendar estimate is justified without those inputs.
Business36/44=82%, delta0; modules100/100demo/100demo/100/89/60/17;
plans100/100/20/33/40/40/0; browser-stage1/4 and finite-plan8/8 remain unchanged.

## This document candidate's validation

Local preflight15 tests,126 browser guard contracts and52 automation contracts
passed, as did progress consistency, links, whitespace, history and unchanged
business-group checks. Independent read-only review found no actionable issue
and separately passed15 preflight tests/progress/whitespace checks. No image,
container, company environment, backend/PG suite or browser execution is claimed
locally for this candidate. Publication and its own exact-head full CI remain
pending; baseline PR181 success is historical evidence, not this document's CI.

## Dependency-input implementation checkpoint — 2026-11-06

The next bounded [npm inventory candidate](offline-npm-dependency-inventory.md)
checks lockfile sources and local artifact bytes without network or extraction.
It does not build images, install dependencies or close runtime acceptance.
Python transitive locks, actual artifact acquisition, container execution and
company log/backup/restore acceptance remain separate work.
