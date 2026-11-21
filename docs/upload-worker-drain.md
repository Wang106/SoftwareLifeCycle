# Cancelled upload worker drain witness

This extends the single test entry from [ingress drain](upload-ingress-drain.md).
It is an isolated SQLite and temporary-file test, not a running HTTP/PG service,
production pause, backup or restore. Existing production code is unchanged.

The real UploadHTTP.receive completes body length and digest validation before
entering its synchronous receive worker. A borrowed reader wrapper blocks the
first read inside actual LocalArtifactStorage.stage using a threading Event.
At that point the real storage has exclusively opened an empty .part and the
worker Session is still open. A thread-safe asyncio Event reports that exact
boundary; no sleep chooses the race timing. Five-second bounds detect test hangs,
not a production deadline. The HTTP synthetic policy remains 60s total/30s idle.

The test freezes its entry, cancels the outer task, and uses a FIFO event-loop
callback checkpoint after cancellation delivery. It asserts that the original
task remains unfinished, entry active count remains one, the only transfer permit
is held, the worker Session is open and the capture callback is refused. The
worker cannot progress until its release Event is set.

After release, the original task raises CancelledError as the production contract
requires; cancellation is not evidence that storage failed. The original request
receipt reports STORED_PRIVATE, the database retains its exact component and state,
and the existing independent disk witness rereads closed bytes, size, SHA-256 and
link conditions. Only after these checks is the drained capture marker invoked.
It creates no snapshot and makes no global-consistency claim. Finally always
releases the worker and awaits the original task before fixture cleanup.

## Regression and limits

Removing only the test entry's active capture guard made the new test fail at
capture (DID NOT RAISE). The original guard was restored, not changed in the final
diff. A test assertion field typo was corrected to existing release_component_id;
no model or production semantics changed. Related local tests, independent review
and exact-head ordinary CI are recorded in the draft PR.

This covers one successful storage worker despite outer cancellation, one runtime,
one event loop and one controlled entry. Existing fake-worker cancellation tests
remain intact. Repeated cancellation, worker errors and reconciliation have their
existing coverage but are not newly proven through real disk in this slice.
Other writers, bypass entry paths, multiple instances, actual PostgreSQL capture,
retention and restore policy remain separate gates. An active count of zero alone
cannot qualify real capture, and STORED_PRIVATE is not scan/distribution readiness.
No production switch, permission, dependency, workflow or runtime configuration is
added. No live deployment, backup/restore, provider operation or company data.
Business acceptance remains36/44=82%,increment0.
