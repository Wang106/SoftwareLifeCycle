# Seven-day API/Web artifact retention preparation

This package prepares an exact upload-candidate inventory and a default-off
synthetic contract workflow. It does **not** implement or enable runtime upload.
There is no image build, new runtime exercise, billing change or artifact retained.
Do not dispatch an older no-retention rehearsal to obtain downloadable media: its
runner output expires and cannot be recovered afterward.

The owner conditionally approved API/Web archives and their necessary handoff
controls in this public repository's GitHub Actions artifacts for seven days,
only after zero incremental cost, content clearance and at most16GiB are verified.
People signed into GitHub with repository read access can download its artifacts.
That is a disclosure boundary, not private transfer to a single recipient.

## What this implementation adds

Use the latest reviewed tool checkout, based here on main
`a6b6e593a27d6146b25a0a3a4ebc498bb0e7c292`. Tool and image source commits differ.
The only accepted image source remains
`e2038a9462770a29254674dd86c0e7b26b26a221`, mapped by the repaired assembler to
`0030_private_upload_sessions`. No compatibility entry is added. Images labelled
with the new tool/main commit are rejected; do not edit the mapping to make them pass.

With an existing, independently trusted five-file handoff on trusted local Linux
storage, invoke the inspector (Python3.12 reference, standard library only):

```sh
python3 -B scripts/offline_media_retention.py inspect "$HANDOFF" \
  --expected-commit "$EXPECTED_COMMIT" \
  --expected-manifest-sha256 "$EXPECTED_MANIFEST_SHA256"
```

The expected commit and manifest hash must come from a separately trusted build
receipt, never from self-hashing an unknown received package. No-argument/help
invocation is inert. Input paths follow the existing no-symlink absolute-path
rules; inputs must be stationary under a trusted execution UID.

The inspector reuses descriptor-pinned strict handoff verification, then hashes
exactly `api.tar`, `web.tar`, `manifest.json`, `evidence.json` and empty `COMPLETE`.
The16GiB input cap includes **all five files**, unlike the old archive-only cap.
No sixth file, private log, database, operator configuration or credential file is
accepted. Copies are not made; no archive is extracted. It rechecks descriptors
and directory membership, attempts each owned close once, and emits an inventory
only after all closes succeed. Original bytes, mtime and inode stay unchanged;
OS access-time updates may occur. Failures are redacted and never retried.

A successful JSON inventory has fixed status
`MEDIA_CANDIDATE_INVENTORIED_NOT_UPLOAD_APPROVED`, source/schema binding, original
manifest digest, five size/SHA256 records, total payload bytes, seven retention
days, and `payload_byte_hours = payload_bytes * 168`. It contains no input paths,
raw content, account billing details, logs or credentials. Exit0 means inventory
success only. Output failure does not authorize rerunning an upload; none exists.

Every result has `upload_authorized=false`, with cost, content clearance, stored
artifact size and actual upload/expiration verification also false. There is no
cost-approved, content-approved or upload switch. The inspector is not a secret
scanner: strict image structure and checksums do not certify layers or dependencies
safe for public disclosure. Even a structurally valid image may contain secrets.

## Size and cost are separate gates

Raw payload bytes differ from GitHub's stored artifact ZIP size. Compression,
headers and packaging overhead must be measured/bounded in a reviewed uploader
before exposure; the16GiB payload check alone is insufficient at the boundary.
The final stored artifact must also be at most16GiB. The maximum seven-day artifact
size/time envelope is2688GiB-hours; it is **not** an allowance or a cost estimate.
No compression savings, available allowance or public-storage exemption is assumed.

[GitHub billing documentation](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
separates free standard public-runner compute from artifact storage. Artifacts and
Packages share an allowance; overage is billed hourly at$0.25/GiB-month. Deleting
later stops future accrual but does not cancel charges already accrued. Account
usage may lag. A present$0 bill or budget is not proof that an unknown-size artifact
can remain seven days at zero incremental cost. Account details remain private.

Public repository retention supports1–90days, with repository/organization limits;
see [GitHub retention settings](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository).
Seven days is the required future request, **not verified expiration of any
artifact**. No billing, budget, repository retention or security setting is changed.

## Default-off workflow and remaining implementation

`.github/workflows/offline-media-retention-preparation.yml` exposes only
`validate_preparation=false`. If explicitly true, it checks the exact selected
**tool** checkout and runs existing bundle/assembler plus new inventory tests.
It uses ubuntu-24.04, contents:read, nonpersistent checkout credentials,10minutes,
and the existing non-cancelling image-rehearsal concurrency group. It never runs
Docker, builds media, uploads/cache artifacts, reads secrets or accesses billing.
Normal PR CI remains unchanged and also collects the new tests. A successful
preparation workflow is not upload approval. This workflow has not been dispatched.

Before adding an uploader or dispatching a reviewed media-producing path, establish:

1. Applicable account allowance, shared current/accrued usage and restrictions,
   candidate stored-size bound and seven-day impact sufficient to establish zero
   incremental cost. A typed approval flag or uploaded account JSON is not proof.
2. Meaningful inspection of actual build inputs/configuration, dependencies and
   image layer contents for the public scope. Do not substitute hash consistency
   for credential/company-file clearance; retain original reviewed bytes/digests.
3. A single reviewed upload path containing only the exact five-file handoff,
   with seven-day retention, bounded stored size and no overwrite/retry behavior.
4. After any authorized upload, inspect actual artifact identity, stored size and
   expiration. Partial/uncertain responses require outcome inspection, not rerun.

This preparation intentionally leaves those operations unavailable until their
conditions are satisfied. No runtime artifact has been produced or uploaded.
The49KB consumer source toolkit is separate and contains no runnable images.
Target OS/architecture/runtime installation and company acceptance remain unconfirmed.

## Evidence

Main `a6b6e593` has the exact reviewed PR231 tree. [Main CI43693857236](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/43693857236)
passed:4148 backend plus3418 subtests,343 PostgreSQL cases without skips,2379 frontend,
16+16 strict browser journeys, migration0030 round trip. Same-main Workers build
passed; Actions deployment43694743897 and continuation43694743883 skipped. Render
remains unrecovered; this package does not change it.

Regression-first collection failed because the new inspector did not exist, then
12 targeted tests passed. Full local suites, independent review and candidate CI
are recorded in the latest handoff; historical main CI is not candidate evidence.
Tests use tiny synthetic archives, not runnable media or billing verification.
Business36/44=82%,increment0; modules100/100demo/100demo/100/89/60/17;
plans100/100/20/33/40/40/0; browser1/4 and finite plan8/8 unchanged.

## Exact local transport bytes

[Transport packaging](offline-media-transport.md) now supplies an explicit local
pack/unpack CLI with exact outer size/SHA-256 and unchanged inner inventory.
It adds no upload step and does not clear cost/content/remote-size/expiry gates.
