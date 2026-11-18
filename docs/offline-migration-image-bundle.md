# Fixed-source migration image handoff

This default-off development capability prepares a separate four-file migration
handoff: `migration.tar`, `manifest.json`, `evidence.json`, and empty `COMPLETE`.
It does not change the five-file API/Web contract or PostgreSQL handoff.
No actual migration image was built, exported, retained or uploaded for this package.

## Identity and trust

The only supported image source is
`e2038a9462770a29254674dd86c0e7b26b26a221`, mapped to
`0030_private_upload_sessions`. The current reviewed tool commit is separate.
The v2 manifest records `tool_commit`, image `source_commit`, and
`required_db_revision`. Receiver `--expected-commit` means the independently
trusted **tool commit**. It must also receive the independently trusted manifest
SHA-256 from this export, not a digest computed solely from received files.
The API/Web receiver's expected commit retains its existing image-source meaning.

The exporter verifies clean Git HEADs and original script blobs before import,
with replacement objects disabled. It invokes the original fixed-source builder
once through isolated Python, with a sanitized environment and bounded stdout.
That builder checks its complete source inventory before building and checks
baked source bytes during its two dependency/default-command smoke probes.
Only the fresh child result is accepted; there is no saved-receipt input.
Both checkouts are rechecked after the child. Image labels, counts and a declared
revision alone do not establish this source binding. The 30 migration and 30
wheel counts corroborate the reviewed source, not substitute for it.

The schema mapping is based on the reviewed source's original Alembic chain
through 0030, not on the current tool's schema constant. Unknown sources and
legacy v1 packages are refused. The receiver authenticates consistency against
an independently trusted manifest digest; it does not independently reproduce
the build, prove publisher identity, scan secrets, or establish content clearance.
The local UID, filesystem, Python/Git executables and Docker daemon must be trusted.

## Future separately authorized export

This command is documentation, not execution permission. It requires a current
clean reviewed tool checkout, a separate clean fixed image-source checkout (both scripts directories must contain
exactly their tracked entries, with no ignored bytecode cache or shadow modules),
Linux/Python3.12+, Docker, network access and enough temporary/daemon storage.
Existing builder prerequisites remain. The output cap is16GiB plus1GiB reserve;
the builder separately checks20GiB free. These are not measured peak requirements.
`DESTINATION` must not exist; do not place it inside either clean checkout.

```sh
python3 -B scripts/offline_migration_image_bundle.py export --run \
  --expected-commit "$TRUSTED_TOOL_COMMIT" \
  --source-directory "$FIXED_SOURCE_CHECKOUT" --destination "$DESTINATION"
```

Without explicit export/run/source-directory arguments no builder is invoked.
The exporter shares the original55-minute budget, reserves the export tail,
and allows90seconds for the original builder's SIGTERM/finally cleanup before
bounded termination. A timeout does not prove daemon work stopped or containers
were removed. No automatic retry, broad cleanup, pull/load/push in the exporter,
or success after uncertain completion. The original builder owns and cleans its
two exact smoke-container CIDs; no database, Alembic command or API is started.
An explicitly authorized future export performs the original builder's downloads,
image build and smoke containers before one immutable-ID `docker image save`.
Partial output is preserved for inspection. COMPLETE is created only after
verification and file close/fsync; failures during completion remain uncertain.

Success reports `tool_commit`, `image_source_commit`, `required_db_revision` and
`manifest_sha256`. Record these independently. An uncertain-completion receipt
contains only the tool commit and manifest digest and is not success evidence.
No output from a historical discarded run can authenticate a future rebuild.

## Receiver-only verification

```sh
python3 -I -S receiver.pyz migration-verify --directory "$RECEIVED_DIRECTORY" \
  --expected-commit "$TRUSTED_TOOL_COMMIT" \
  --expected-manifest-sha256 "$TRUSTED_MANIFEST_SHA256"
```

Or run the reviewed `scripts/offline_migration_image_bundle.py verify` with the
same arguments. The source toolkit includes this module and its existing pure
file dependencies; it excludes the migration builder/fetch/context modules.
Verification performs no Git, Docker, subprocess, network, extraction or writes.
It requires Linux/Python3.12+ and `/proc/self/fd`, checks exact names and stable
file descriptors, archive structure/layers/config, size/digests and compatibility.
The toolkit command forces verify mode and rejects export/run/source-directory.
Keep the toolkit archive digest separate from the handoff manifest digest.

A verified archive is not an installed runtime, executed migration, initialized
schema or company acceptance. OS/Python/Docker installation, actual media build,
content clearance, transfer/retention cost and authorized database initialization
remain separate prerequisites. No upload workflow or permission override is added.
