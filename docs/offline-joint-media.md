# Joint offline media verification

`offline_joint_media.py` checks actual API/Web, PostgreSQL and migration handoffs
in one filesystem-only operation. It produces a four-image index only after all
existing strict validators and final identity checks pass. It never builds,
exports, loads or runs images, connects to a database, writes files, extracts
archives, creates credentials or uploads media. No actual runtime media was
produced or delivered by this development package.

## Three independent trust inputs

Each handoff directory and manifest SHA-256 must come with an independently
trusted receipt. A digest copied from a received manifest or adjacent checksum
file does not establish trust. Commit meanings differ:

| Handoff | Expected commit | Image compatibility |
| --- | --- | --- |
| API/Web | image source e2038a9462770a29254674dd86c0e7b26b26a221 | reviewed source mapping to schema0030 |
| PostgreSQL | separately trusted exporter tool commit | original fixed PostgreSQL repository digest/config/layers |
| Migration | separately trusted exporter tool commit | manifest image source must be e2038a94/schema0030 |

The PostgreSQL and migration tool commits may differ from one another, the image
source and the receiver toolkit commit. They are not inferred from the toolkit.
The original five-file API/Web and four-file PostgreSQL/migration contracts stay
unchanged. Do not put this index, credentials or additional records inside them.

## Explicit verification

Linux/Python3.12+ and `/proc/self/fd` must already be available. Use trusted local
storage with no concurrent writer. Supply three distinct, non-nested absolute
directories. No runtime or Docker executable is needed.

```sh
python3 -B scripts/offline_joint_media.py verify \
  --api-web-directory "$APP_HANDOFF" \
  --api-web-expected-commit "$APP_IMAGE_COMMIT" \
  --api-web-manifest-sha256 "$APP_MANIFEST_SHA256" \
  --postgres-directory "$PG_HANDOFF" \
  --postgres-expected-commit "$PG_TOOL_COMMIT" \
  --postgres-manifest-sha256 "$PG_MANIFEST_SHA256" \
  --migration-directory "$MIGRATION_HANDOFF" \
  --migration-expected-commit "$MIGRATION_TOOL_COMMIT" \
  --migration-manifest-sha256 "$MIGRATION_MANIFEST_SHA256"
```

The source-only receiver toolkit exposes `media-set-verify` with the same nine
named arguments, omitting the standalone `verify` word:

```sh
python3 -I -S receiver.pyz media-set-verify --help
```

An independently trusted digest of the whole toolkit is also required before
executing it. The toolkit is not a Python, Docker or Windows installer.
Invoking the standalone tool without arguments is inert. Runtime/export/load/upload flags
are rejected; the receiver entry forces verify mode. Ordinary syntax and policy
errors return2 with fixed diagnostics, without exposing paths or rejected data.

## What is actually checked

All three directories, their ancestors and13 files are opened with the existing
no-follow descriptor protections before content validation. Lexical nesting,
directory inode aliases and aliases to another input's ancestors are rejected.
Existing file checks reject symlinks, hardlinks, non-regular files, extra names,
nonempty COMPLETE markers and observable changes. Each original archive format,
config, ordered layer/hash policy and independently expected manifest digest is
validated without relaxing its existing gates.

One600-second, non-extending budget covers opening, all validators, final checks
and close. An existing alarm is refused. No individual wrapper resets that
budget. All13 local files, including metadata, count toward a16GiB payload cap.
This is a bounded local support limit, not an upload authorization or a statement
about transport size, remote stored size, billing allowance or disk peak usage.

The index projects only verified fields: four unique immutable image IDs,
archive names, sizes, digests, platforms, handoff roles and the correctly typed
source/tool identities. The PostgreSQL identity is taken from its verified
contract, not a user-provided image label. API/Web and migration share the exact
reviewed e2038a94/schema0030 mapping. All inputs are rechecked together after
validation, before descriptor close and successful return. Output/close/time
failures must not be reported as success.

## Success is limited

Exit0 with `MEDIA_SET_VERIFIED_NOT_INSTALLATION_READY` means the four image
archives passed these checks together. `handoff` values in the index are logical
roles, not newly created paths. `payload_bytes` is the total local13-file size.
The index is a point-in-time report, not a saved authorization or reusable proof
that later paths still contain these bytes. Any future importer must reverify.

`installation_ready`, `database_migrated`, `database_readonly_role`,
`runtime_verified`, `company_acceptance`, `content_clearance_verified` and
`upload_authorized` remain false. No existing operator declaration is changed.
Hashes are not signatures, secret scans or independent publisher authentication;
trusted descriptors are not snapshots against a hostile local user.

Actual complete retained media, authorized transfer/retention with verified cost
and content conditions, target runtime installation, database initialization,
read-only role provisioning and company acceptance remain separate work.
The application preflight still requires a genuinely preprovisioned database;
passing this media check cannot bypass that requirement. No automatic installation
or permanent BLOCKED declaration checklist is introduced: valid actual file sets
can pass this narrower integrity check without claiming runtime readiness.
