# Offline read-only configuration preflight (preparation only)

## Scope and current target decision — 2026-10-26

The user selected a **candidate** physical Windows Server 2016 Standard 1607,
14393.6796, x64, 16 GB → Hyper-V → Ubuntu 24.04 amd64 VM → Docker Engine/Compose
route. Observed memory use 27%, C:75.6 GB and D:94.7 GB free are snapshots, not
capacity or peak-load approval. No Hyper-V/VM/Docker installation, restart, switch,
firewall, network, credential, identity, company database or production operation
is authorized or performed by this development package. The personal Mac is not used.
Development and tests can continue before that server is configured.

This package implements a **local Linux read-only rehearsal configuration renderer**,
not an offline installer or complete deployable bundle. The existing development
`docker-compose.yml` and entrypoint remain unchanged. Do not use the development
compose in the company environment: it builds/downloads, has development credentials,
public binds, seed/write defaults and an automatic migration entrypoint.

## What is implemented

`python scripts/offline_readonly_preflight.py /path/to/operator-owned-bundle`
uses only Python 3.12 standard library and reads files. On valid inputs it emits
Compose JSON to stdout and `CONFIGURATION_ONLY` to stderr. Invalid/missing inputs
exit 2 with a redacted diagnostic and **no Compose output**. It never calls Docker,
starts/loads/builds/pulls images, installs packages, extracts archives, creates files,
connects to PostgreSQL or a network, initializes/migrates/seeds a database, or changes
credentials. Review output before saving it; this command is not startup authorization.

Copy the two `deploy/offline-readonly/*.example.json` files into a private working
bundle as `manifest.json` and `operator.json`. They intentionally fail validation:
there are no real image identities/checksums and database readiness flags are false.
Do not commit the operator bundle, images, database connection or rendered local paths.
No credentials are generated or supplied in this repository.

Required operator-owned inputs, after separate approval:

- Exactly one uncompressed, single-image `docker save` archive per API/web service.
  Manifest records exact 40-hex source commit, linux/amd64, full immutable image ID
  (`sha256:<config digest>`), archive byte size and SHA-256. API and web both bind the
  same source commit; image config must carry `org.opencontainers.image.revision`.
- Validator checks archive bytes, config digest, actual platform/revision label and
  every uncompressed layer hash against `rootfs.diff_ids`; rejects traversal,
  duplicate paths, links and special members without extracting them. This supports
  this bounded docker-save format only, not OCI layouts or arbitrary registry exports.
  Checksums/labels prove consistency, **not provenance authentication or safe image
  contents**. Obtain all files/manifest from a separately trusted reviewed build.
- Reviewed image build must not bake application settings, credentials, `.env`,
  identities, provider endpoints or public API fallback URLs into layers. Only a
  narrow baseline runtime environment allowlist is accepted in image config.
  Layer hashes do not inspect application content or prove these build requirements.
  Existing Dockerfiles alone do not establish this new bundle's provenance/acceptance.
- Operator `database.env`, mode 0600 or stricter on Linux, containing exactly one
  literal `DATABASE_URL=postgresql+psycopg://<read-only-role>:<operator-password>@127.0.0.1:5432/<synthetic-db>`
  line. No comments, substitutions, extra env keys, URL options, remote host, default
  password or fallback database configuration. Paths remain inside the bundle;
  symlinks and Compose-interpolated `$` paths are rejected. Percent-encode URL password delimiters. This file remains
  an operator secret; never paste its contents into chat, commits, logs or CI.
- Explicit `database_preprovisioned=true`, `database_readonly_role=true` and
  `data_classification=synthetic-only` are declarations, **not verified facts**.
  An independently authorized operator must already have provisioned PostgreSQL,
  exact schema `0029_changeover_batch_history`, a non-owner/non-superuser SELECT-only
  role without write/CREATE/TEMP privileges, and approved synthetic data. This
  package does not create or grant that role or provide a database installation.

## Fixed rendered behavior and limits

- API/web images are immutable local IDs, `pull_policy: never`, `platform: linux/amd64`;
  absent local images must fail rather than download. There is no `build`, PostgreSQL
  service, data volume, automatic migration, seed, image load or package fetch.
- API explicitly replaces the image entrypoint with Python/uvicorn. It never calls
  existing `entrypoint.sh`/Alembic/seed. `READ_ONLY_MODE=true`, both seed switches false,
  authentication disabled and offline administrator disabled. Readiness must later
  verify actual schema, not assume it from configuration. `PGOPTIONS` requests
  read-only transactions; SQL role permissions are still mandatory defense in depth.
- Web explicitly runs Next with disabled browser identity/session and **all** current
  submission gates. Runtime API is `http://127.0.0.1:8000`; public API fallbacks cleared.
  A regression detects newly introduced gates so they cannot silently be omitted.
  Build-time `NEXT_PUBLIC_*` contents still require actual image/build inspection.
- Both processes explicitly bind `127.0.0.1`, with no remote listener or automatic
  reverse proxy. Linux `network_mode: host` avoids creating a Docker bridge/network,
  **shares the host network namespace**, and does **not** enforce offline operation,
  block outbound traffic or isolate access to host services. Host egress policy and
  company networking are separately approved operator responsibilities. Do not expose
  this unauthenticated read-only profile to other machines or real company data.
- Read-only root filesystems, nonroot UID/GID65532, all capabilities dropped,
  no-new-privileges and bounded temporary `/tmp`; no automatic restart. Image-declared
  writable `VOLUME` metadata is rejected. Runtime image
  permissions and Next/cache behavior remain untested. Healthcheck is disabled in
  generated config rather than inheriting unknown image commands; actual health and
  API/schema acceptance must be explicit in the later supervised rehearsal.
- Requires Linux Docker Engine and **Compose >=2.30.0** (`env_file.format: raw`). This
  is not Docker Desktop for Windows Server and not WSL2 on Windows Server 2016.
  No Docker executable is available in the current cloud workspace; Compose parsing,
  image loading/start, process binds, denied database writes, application rendering,
  real offline operation and company browser acceptance are **not tested here**.

## Verification and next gate

`python backend/tests/test_offline_readonly_preflight.py -v` executes standard-library
unit/CLI tests without Docker, database or network. The synthetic tar test fixtures
are explicitly **not runnable container images**. Existing unchanged full backend,
PostgreSQL and frontend CI remains mandatory for the exact implementation head.

Next bounded package, only after this one closes: reviewed linux/amd64 image packaging
and an isolated synthetic Linux runtime rehearsal in an explicitly authorized Docker
build/test environment. Need real archives, pinned build provenance, offline target
runtime packages and verification of Compose rendering/no-pull, process exposure,
readiness/schema, read-only SQL grants, no seed/migration, unchanged data and bilingual
browser behavior before calling any bundle runnable. That is not authority to install
or restart the user's server. IT should separately approve Hyper-V/virtualization,
backup/maintenance window, capacity, import method and later network/HTTPS policy.
Identity/OIDC, real business writes, real company data, retention/RPO/RTO, production
operations and actual company acceptance remain closed/unaccepted. No roadmap or
plan milestone is checked merely because this preparation exists: **36/44=82%**.
