# Exact local transport archive preparation

`scripts/offline_media_transport.py` forms one uncompressed canonical USTAR file
from an existing validated five-file handoff. It reads back actual output bytes,
checks each inner size/hash, and reports exact outer size/SHA-256 alongside the
unchanged #232 inventory. This is local preparation, with no uploader, build,
container, network operation, billing override or content-clearance claim.

Only image source `e2038a9462770a29254674dd86c0e7b26b26a221` is accepted, using
the reviewed schema0030 compatibility map. Tool HEAD is a separate commit.
The independently trusted **handoff manifest digest** must come from reviewed
same-run build evidence; an adjacent received hash is not a trust anchor.
The **transport digest** identifies the outer file and never replaces that trust.

## Explicit local commands

Default invocation is inert. Paths must be absolute, on a trusted local Linux
filesystem, without symlinks; this is not a hostile-user filesystem boundary.
Existing output paths are refused. The source is preserved.

```sh
python scripts/offline_media_transport.py pack /approved/handoff /approved/media.tar \
  --expected-commit e2038a9462770a29254674dd86c0e7b26b26a221 \
  --expected-manifest-sha256 TRUSTED_INNER_SHA256
python scripts/offline_media_transport.py unpack /approved/media.tar /approved/received \
  --expected-commit e2038a9462770a29254674dd86c0e7b26b26a221 \
  --expected-manifest-sha256 TRUSTED_INNER_SHA256 \
  --expected-transport-sha256 TRUSTED_OUTER_SHA256
```

Record successful receipts separately. A failed/interrupt/close/reporting result
is unconfirmed: inspect the exact owned output, never overwrite, resume or blindly
retry. No automatic deletion occurs. Extraction validates the full outer framing
and digest before mkdir, then validates the four inner payloads and closes them
before creating COMPLETE. A later marker/parent close or receipt failure can leave
a valid completed directory with an unconfirmed outcome; presence alone is not a
successful operation receipt.

The archive has only COMPLETE, api.tar, evidence.json, manifest.json and web.tar,
in fixed order, with canonical regular-file headers. Member modes are0600;
extraction directories0700. Names, duplicates, links, directories, devices,
PAX/GNU metadata, nonzero padding, truncation and trailing bytes are refused.
There is no generic tar extraction or compressed expansion. Each member is at most
8GiB minus1 byte (USTAR octal limit), and the entire outer archive must be<=16GiB,
including headers and padding. A destination free-space check reserves1GiB beyond
the expected local copy. This is not a target laptop/server capacity estimate.

## Future direct-upload compatibility, not an upload implementation

Upstream [v7.0.0](https://github.com/actions/upload-artifact/releases/tag/v7.0.0)
resolves to `bbbca2ddaa5d8feaa63e36b76fdaad77386f024f`.
Its [immutable action definition](https://github.com/actions/upload-artifact/blob/bbbca2ddaa5d8feaa63e36b76fdaad77386f024f/action.yml)
supports `archive:false` for exactly one file, using the filename as artifact name.
A future separately reviewed path could upload these known bytes without another
ZIP layer. The action uses Node24; its pinned README requires runner>=2.327.1.
Any future execution must verify runner compatibility, exact action revision,
single-file selection and post-upload identity/size/digest/expiration. This package
adds no action invocation or workflow change and has not tested upload behavior.

`transport_bytes_verified` is local only. The existing inventory's
`stored_artifact_size_verified`, cost/content/expiration flags and upload permission
remain false. Before any actual upload: establish zero incremental cost accounting
for shared usage and meter latency, public content clearance (hashes are not a
secret scan), <=16GiB total stored bytes and exactly seven-day retention. Public
repository readers may download media. No databases, credentials, company files,
raw private logs or workspace archives belong in this handoff.

## Evidence and remaining boundary

PR233 main `bce42c2` CI43710387455 passed; one owner-authorized temporary run
43713722202 passed on attempt1 in2m37s. It measured1,360,327,335 payload bytes,
removed both dependency-smoke containers and retained zero media. Those discarded
bytes and hashes cannot validate a future rebuild. No new image build or dispatch
is authorized by this implementation package. Tests use synthetic tar fixtures.

The Windows10 Home x64 staging laptop reportedly has>50GB free;100GB is only a
proposal. Direct intranet copy replaces USB; independently compare the outer hash
before/after transfer, then use the inner validation gates. No laptop/server
installation, actual transfer, physical offline operation or company acceptance
has occurred. This Linux tool is not a confirmed Windows installer.
