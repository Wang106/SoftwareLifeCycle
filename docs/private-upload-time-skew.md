# Synthetic cross-time upload content acceptance

The existing joint retained restore binds hashes and pairing evidence from one
invocation and rejects arbitrary cross-pair substitution. That mechanism is not
changed or weakened. The #261 witness verifies one restored object against an
existing database record, not completeness across a restored target scope.

This test-only addition exercises a distinct content consistency obligation.
A synthetic SQLite target first commits upload A. Its bytes are copied into an
owned temporary media root and an independent digest is retained in test memory.
The target then commits B as STORED_PRIVATE; a digest of the complete target
record projection is retained separately. Both supplied fixture projections pass
their own integrity checks. These hashes are test corruption checks, not signatures
or provenance, pairing authority, database dumps or backup-format verification.

A still passes the actual read-only service inspect and independent disk witness.
B's historical receipt also exists, but the old media has no B. A complete-scope
content check therefore rejects. The failure leaves media bytes, target record
projection and audit IDs unchanged; it does not repair, upload or return partial
success. An aligned A+B media target succeeds. Empty media and a scope with no
committed entries cannot produce vacuous acceptance.

## Expected set and limits

`verify_scope_restored` lives only in backend/tests/private_upload_restore.py.
It queries every STORED_PRIVATE row in the explicit synthetic storage scope,
ordered by request ID. It takes no media manifest or caller-selected request list;
media contents cannot narrow the expected set. Each row is checked through the
existing real service inspect and #261 read-only disk witness. No production
catalogue, permission bypass, upload or operator command is added.

The fixture exclusively owns its small database and forbids concurrent writers.
The helper rolls back its dedicated test Session between observations; it is
not a general-purpose side-effect-free API for callers with pending writes.
A final requery rejects observed set/receipt changes, but sequential reads are
not an atomic snapshot. There is no claim about scalable pagination, concurrent
backup consistency, cross-scope completeness, actual DB dump/restore, production
readiness or media provenance. Non-STORED_PRIVATE lifecycle reconciliation is
outside this deliberately committed-content slice. Existing authorization stays
active; all supplied test records belong to the synthetic authorized principal.

## Evidence

The initial regression failed because the complete-scope witness was absent.
Four new synthetic cases and the related suite pass:121 tests+16 subtests.
No backup/restore command, new service or PostgreSQL instance was invoked locally.
Ordinary existing CI is unchanged and its final evidence is recorded in the PR.
Independent review covers the test helper, completeness boundary and technical
records. No production code, workflow, configuration, permissions, billing,
Render, intranet or dependencies are changed. Existing public history remains.

Actual consistent database/media capture, supported restoration and target
acceptance remain missing gates. Historical e2038a94 images remain outside
Next16.4.5 source-patch coverage. Business36/44=82%,increment0.
