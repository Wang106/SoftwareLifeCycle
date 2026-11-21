# Single-instance synthetic upload ingress drain

A closed preflight database Session does not mean an admitted upload has ended.
This test reuses `test_private_upload_http.py`'s real UploadHTTP.receive,
coordinator, isolated synthetic SQLite fixture and tracked Session pattern.
There is no HTTP server, real identity provider, PostgreSQL instance, backup or
restore operation. The test-only entry is not wired to production.

## Event-controlled witness

A and B have independent valid reservations with different request/object IDs.
The runtime has two transfer permits. A returns its first body fragment, then
signals an asyncio Event from the second body-read callback and waits on another
Event. At that exact point its preflight Session has closed on its owning worker,
no Session transaction is held, the last body bytes have not arrived and no files
exist. The wrapper counts the entire awaited receive call as active.

The test freezes only this entry and verifies that the capture callback is NOT
called. A spare runtime permit can be acquired and returned, so B is not rejected
by capacity exhaustion. B is rejected by the frozen test entry before body reads
or another Session opens. Its original independent reservation remains RESERVED
and no B bytes exist. This does not prove a production pause or other entry paths.

Releasing A's Event allows the unchanged receive/coordinator to finish. Original
request/object identity and STORED_PRIVATE receipt are checked, recovered through
the original request ID, then actual temporary disk bytes, length, SHA-256 and
link conditions are independently reread using the existing disk witness. Only
then does the test call the now-drained capture marker, exactly once. That marker
writes no snapshot and does not certify consistency. The entry remains frozen.

Event handshakes establish ordering; no sleep chooses a race timing. Five-second
wait bounds detect a hung test, not a production timeout policy. Existing finite
runtime deadlines remain enabled with synthetic policy60s total/30s idle. Finally
always releases A's event and awaits its task before fixture cleanup.

## Regression and limits

The initial baseline wrapper omitted its active-request capture guard. The new
regression failed because capture was allowed while A was still waiting. Adding
that one test-only guard makes the focused and related suite pass:148 tests,
no skips. Existing test assertions and production implementation are unchanged.
Independent review and exact-head ordinary CI are recorded in the draft PR.

This is one event loop, one runtime and one controlled wrapper entry. Other
writers, direct calls bypassing it, multiple workers/instances and cancellation
after the storage worker starts are NOT validated here. Existing thread lifetime
tests are not replaced or duplicated. Failed/uncertain uploads need lifecycle
reconciliation; an active count of zero alone cannot qualify a real capture.
No production pause flag, database lock, permissions, workflow, dependency,
configuration, Render/server operation or real backup policy is added.

Next missing gate remains real all-writer admission/drain enforcement and safe
capture/lifecycle integration under a separately reviewed scope. Historical
e2038a94 images remain outside Next16.4.5 source-patch coverage; prior CI timing
causes remain unknown. Business acceptance36/44=82%,increment0.
