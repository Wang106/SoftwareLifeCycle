# Synthetic write-pause and capture ordering contract

This is a design and executable test model, not a maintenance command, database
lock, backup application or production write switch. #262/#263 checked content
mismatches in quiescent fixtures; they did not establish a real quiescent window.
`private_upload_loopback.mark_quiescent` checks its owned server/permit for test
cleanup, not every service/process/writer or a backup window. No equivalent
cross-writer pause/capture sequence was found in current main0bddf9c9.

## Known source paths and gaps

| Category | Current source and effects | Required future coverage |
| --- | --- | --- |
| HTTP reservation | `app/api/private_uploads.py` POST reservations -> `UploadHTTP.reserve/call` -> `PrivateUploadService.reserve/_record`: session and audit commit | Block admission before any new reservation, including queued workers |
| HTTP content | PUT content -> `UploadHTTP.receive`; network buffering, owned worker, coordinator receive | Drain admitted network work and actual worker completion, not just cancelled HTTP tasks |
| Coordinator | `private_upload_sessions.py` receive/_transition/_uncertain/_record: RECEIVING, STAGED, PUBLISHING, STORED_PRIVATE or reconciliation state, audit commits | Direct trusted callers must use the same enforced boundary; per-instance `_busy` is insufficient |
| Byte primitive | `local_artifact_storage.py` stage creates retained .part; commit links .blob and fsyncs | Cover all instances/processes using a root; no delete/GC path currently exists; failed bytes remain |
| Related DB writers | `application_component_declaration.py` creates ReleaseComponent; `snapshot.py` copies SnapshotArtifact; release/governance/security writers change parent state, authority or audit; `write_contracts.py` inventories registered write routes | Whole-database capture requires inventory and exclusion of all DB writers, not only private upload routes |
| Own browser-session registration | `app/api/browser_sessions.py` POST `/api/v1/security/me/browser-sessions`: authenticated active USER creates BrowserSession and BROWSER_SESSION_CREATED audit in one commit; exact replay does not create a second row | Separate database writer, explicitly allowed by `main.py` read-only-mode exception; upload admission does not cover it |
| Own browser-session first revocation | POST `/api/v1/security/me/browser-sessions/{session_id}/revoke`: exact principal/token binding, first revoke sets revoked_at and commits BROWSER_SESSION_REVOKED audit; replay returns success without another mutation | Separate database writer; measure fresh pre/post durable state, not merely successful replay response; preserve normal logout/security semantics |
| Operator paths | `seed.py`, `seed_release_demo.py`, `seed_release_evidence.py` create Artifact/component rows; Alembic/schema/operator/direct SQL or same-UID file tools can bypass HTTP | Disable/exclude seed, migrations, maintenance, scheduled workers and external writers for the window with independently verifiable enforcement |

Private upload does not create Artifact or distribute bytes. Frontend
`private-upload-proxy.ts` forwards reserve/content to the backend; stopping one
browser or relay is not sufficient. GET context/receipt and service inspect are
read-only here (filesystem access-time effects excluded), not upload resumptions.
The source inventory is a review of known code, not discovery of actual running
processes, credentials, remote writers or exhaustive runtime authority.

`UploadHTTP.permits` is process-local capacity, not a global maintenance barrier.
`owned_worker` retains admission during cancellation until the synchronous task
finishes. A missing response or cancelled client does not prove storage stopped.
A disabled flag, timestamp, lock file, operator statement or free permit alone
must not be accepted as enforced pause. This package adds none of those controls.

## Future acceptance sequence

1. Establish exact deployment/root/DB identity and all writer authorities. Unknown
   or uncovered writers prevent starting a consistent capture claim.
2. Close new admission across every writer atomically relative to its admission
   mechanism. Keep authority over that barrier throughout the window.
3. Wait for already admitted work, workers, transactions and byte operations to
   finish. Unknown/cancelled work remains pending until independently resolved;
   do not free ownership early. Record unresolved durable phases separately.
4. With no writer able to enter, capture DB and media in the same held window,
   binding exact targets and retained byte integrity. Their order alone provides
   no consistency if the barrier is not real.
5. Verify the retained pair, full intended scope and lifecycle policy while the
   barrier remains held. #263's committed-only assumption cannot silently absorb
   staged/reconciliation bytes. Real capture format/durability remain undecided.
6. Recheck writer/barrier identity and drain state before controlled release.
   Any unknown/error invalidates success. Keep closed pending an explicit safe
   recovery decision; no automatic resume, retry, deletion or cleanup is designed.

## Executable synthetic boundary

`backend/tests/synthetic_capture_window.py` owns a closed in-memory World and six
fake writer lanes. Its pause requires those exact object identities, not labels
or caller-supplied approval tokens. Fake admission rejects new starts after pause;
existing work can finish before drain. Revision/admission/active-work observations
are checked before and after each synthetic callback. DB capture precedes media,
then verification and release. Errors or changed observations invalidate the
window and close only its owned fake writers. No external adapter is supplied.

The model is single-threaded and assumes trusted test code. It does not prove
completeness outside World, atomic multi-process exclusion, durable crash state,
real I/O cancellation, truthful callbacks, dataset integrity or a production
pause. `synthetic_sequence_complete` is only an ordering result. The fields
`production_pause_verified`, `actual_capture_verified`, and `atomicity_verified`
are always false, including the positive path. No receipt from this model can
qualify a real backup. A process crash or missing enforcement remains unhandled
outside the model, not a simulated success.

## Validation and remaining gate

The new regression first failed for the absent contract module.25 pure tests
cover stable completion, missing/replaced writer coverage, old work drain, late
admission refusal, unexpected mutation/reopen or exception during each phase,
early release and wrong order. No backup/restore command, DB service, filesystem
capture, browser, process, Render action or new workflow is run by these tests.
Independent rereview and remote CI remain separate publication gates.

Next missing gate is an independently reviewed real writer-enforcement and drain
integration for a specified target, plus consistent capture/verification semantics
and staged-state policy. This requires its own scope; it is not enabled here.
Historical e2038a94 images remain outside Next16.4.5 source-patch coverage; prior
CI timing causes remain unknown. Business acceptance36/44=82%,increment0.

## Model ownership repair

Independent review reproduced two Windows sharing one World: the second could
release while the first was still drained. New regressions gave4 failures and20
passes. World now holds one owning Window. A second cannot acquire or release
it; stale/nonowner errors cannot alter admission. Failure leaves admission closed
and discards observations; ownership becomes available only after callbacks
unwind. A fresh Window can explicitly reacquire the closed pause, but must repeat
drain/capture/verification. This is not automatic production recovery. Nested
callbacks cannot transfer ownership early. Formatted errors suppress the original
exception chain, not Python-object or traceback-local secret erasure.

Final25 synthetic tests; related154 tests+16 subtests. Remote CI and draft PR not
yet performed. Current workflow automatically runs on main push or PR, not feature
push. Publication order is now confirmed: create a draft to trigger ordinary CI,
then verify its exact head and update the PR evidence; no manual dispatch needed.

## Upload-entry quiet versus database quiet

The test `test_first_revoke_writes_while_upload_test_entry_is_drained` reuses the
signed identity_client fixture (SQLite locally, existing isolated PostgreSQL in
ordinary CI) and its same Session factory for a real UploadHTTP instance. Its
existing test-only entry starts with no admitted uploads, is frozen, and accepts
an entry-drained marker. It does not pretend an upload ran or install a production
pause. Session registration and first revocation go through the unchanged signed
HTTP routes and the same database while read_only_mode remains true.

Before the first revoke, a new database Session observes revoked_at NULL and zero
matching revoke audits. Afterwards another Session sees revoked_at set, exactly
one new total audit and exactly one revoke audit linked to that session and actor.
The creation audit remains singular. The upload entry remains frozen/empty, its
permit is free and its temporary root is empty. No replay is used as write proof.
An initial negative probe expecting revoked_at to remain NULL failed, disproving
the all-database-quiescence inference; final regression asserts the actual write.
This is a scope counterexample, not a production bug or a new maintenance lock.

The six-lane fake World above is unchanged and does not gain runtime coverage by
this inventory addition. An uncovered session writer cannot be counted as paused
or drained for a whole-database-no-writes claim. Attachment-writer quiet is a
narrower claim. A normal session commit does NOT by itself invalidate a pg_dump
MVCC snapshot or prove attachment inconsistency. No dump/restore/snapshot is run,
and this package does not block login/logout or broaden any permission. Future
capture design must specify whether whole-DB quiet is required and how legitimate
session operations are handled; no policy is selected by this synthetic test.
