# Closed synthetic private-media acceptance

This test-only witness complements #262's missing-media direction. A synthetic
old target database contains only committed A; a supplied newer media fixture
contains valid A and a separately generated B pair. A's real read-only inspect
and disk witness passes. Independently retained database/media projection hashes
also pass, but the closed-scope check rejects the extra B without deletion,
repair, retransmission or returned partial acceptance. These projections are not
actual database dumps, time snapshots, signed provenance or backup-format proofs.

## Deliberately restricted scope

`verify_closed_scope_restored` is only in backend/tests/private_upload_restore.py.
The fixture exclusively owns its entire small root and database, forbids concurrent
writers and other storage users, and admits only nonempty STORED_PRIVATE records
in the exact scope. It derives both expected aliases from every database object,
never from a media manifest. It checks exact root names before and after the
existing full-scope byte/authorization witness, and rechecks the database rows.
It reads no unknown entry and performs no cleanup. Known files still undergo
real storage inspect and independent closed-file length/hash/link checks.

Production LocalArtifactStorage deliberately retains `.part` aliases and any
bytes created before failure. RESERVED, RECEIVING, STAGED, PUBLISHING and
RECONCILIATION_REQUIRED reconciliation is outside this slice. A noncommitted row
makes this witness inapplicable; it does not prove an orphan or authorize deletion.
Extra media can be legitimate outside the closed fixture assumptions. There is
no new production inventory policy or claim that arbitrary real backups must
contain exactly two files per committed row. Root/scope provenance and exclusive
ownership are trusted test setup, not inferred from names or hashes.

The dedicated test Session must have no pending writes: snapshots use rollback.
Before/after comparisons are sequential, not atomic or a concurrency guarantee.
No database backup/restore command, new service, real target, production data,
permission, workflow, dependency, configuration or deployment change is included.

## Evidence and remaining gate

Against the original scope witness, the new synthetic cases gave7 failures and
1 pass: absent extra-entry/state rejection. The new helper and related suite
pass129 tests+16 subtests. Cases cover aligned A, extra B, stage/object/unrelated
files, directory/symlink entries, and unsupported RESERVED records. Independent
review and exact-head normal CI are recorded in the draft PR.

Actual consistent DB/media capture, lifecycle reconciliation policy, supported
restoration and target acceptance remain unverified. Historical e2038a94 runtime
images are not covered by the Next16.4.5 source patch. Business36/44=82%,delta0.
