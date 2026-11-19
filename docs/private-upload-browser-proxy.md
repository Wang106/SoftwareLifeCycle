# Default-off same-origin private upload relay

This slice connects the existing private HTTP coordinator to authenticated same-origin server routes. It adds no file picker, Artifact creation, download, scan verdict, operational settings or deployment. Only synthetic test identities and bytes have been exercised.

## Contract

All routes are dynamic server routes. `PRIVATE_UPLOAD_MODE=enabled` alone is insufficient: existing encrypted OIDC session configuration and exact `PRIVATE_UPLOAD_APPROVED_API_BASE_URL` / `PRIVATE_UPLOAD_APPROVED_APP_ORIGIN` matches are required. No values are enabled in repository configuration. Default-off and rejected origins perform no upstream request and do not consume file bytes. Credentials stay server-side.

| Same-origin route | Method/body | Fixed API operation |
| --- | --- | --- |
| `/auth/private-upload-context` | POST JSON `{component_id}` | GET original private component context |
| `/auth/private-upload-reserve` | POST exact reservation metadata | POST reservation, never automatic retry |
| `/auth/private-upload-content?request_id=...` | PUT `application/octet-stream` | One bounded PUT to original request |
| `/auth/private-upload-receipt` | POST JSON `{request_id}` | GET original private receipt only |

Metadata and upstream JSON responses are limited to 32 KiB; duplicate metadata keys are rejected. Binary content is not JSON, multipart or base64. Its maximum is 8 MiB and the smaller current backend admission limit. Before consuming bytes the relay authenticates the session, rejects read-only operation, checks the original reservation owner/state, and requests the current authorized component context. It checks original component/storage scope/size/digest, then rechecks current identity after ingress. Backend authorization and freshness checks remain authoritative; context hashes are consistency evidence, not credentials. A reservation receipt does not contain the original context digest, so the relay does not invent that binding from a later context.

A single monotonic 120-second budget spans the handler. Actual nonempty byte progress alone renews a 10-second idle deadline. Identity lookup, including its body, has an additional 5-second maximum within the shared budget. Both total and per-operation deadlines are checked after await, not only by timer callbacks. This bounds the relay's waiting; cancelling does not establish that backend work stopped.

At most two handlers own admission in one process/isolate. Duplicate in-flight actor/request pairs are rejected within that isolate. Pending fetch/read/cancellation work retains admission until it actually settles, including cleanup added during unwinding. A permanently unresolved operation can therefore retain a slot. This is not a global fleet quota, durable replay ledger or storage capacity reservation.

The bounded final `Uint8Array` provides a known-length upstream body on Workers. Manually setting Content-Length on an arbitrary stream is not a substitute. This feature's complete upstream chain uses manual redirects and rejects 3xx; other existing proxies are unchanged. No inbound cookies, arbitrary URLs or provider response headers are forwarded. Public errors are projected and private/no-store.

## Uncertain outcomes and recovery

Sending all bytes is not proof of storage. After a successful PUT the relay validates the stored response and independently reads the original receipt. Only exact `STORED_PRIVATE` evidence establishes private storage; it does not mean scanned, distributable, published or business-approved.

Each handler performs at most one write attempt. An uncertain reservation or content response requires original-request receipt lookup only. Receipt recovery performs no POST/PUT, creates no new request ID and never resends bytes. A recovered `RESERVED` state does not authorize a retry. The future UI/caller must retain this one-attempt lock; these stateless endpoints do not durably prohibit a separate HTTP request. Backend durable one-shot transitions remain unchanged. No UI is delivered in this package.

## Verification and limits

Synthetic Node tests cover strict metadata, identities, scope, hashes, lengths, refusal-before-body, smaller limits, lost replies, final receipts, deadlines, concurrency and cancellation ownership. The local workerd test bundles the actual handler and supplies an in-memory API double. It uses the repository compatibility date, verifies 65,539 binary bytes including non-UTF-8 data, Content-Length, SHA-256 and original receipt.

The first local workerd configuration omitted `cf:false`; Miniflare could attempt its implicit `https://workers.cloudflare.com/cf.json` metadata request. That result is not zero-egress evidence. The revised test explicitly sets `cf:false`, routes all Worker egress to the local double or a throwing handler, and rejects non-loopback Node dispatcher requests before transmission while asserting zero attempted external destinations. No rejected historical test-output operation is retried.

Local simulation, production build, ordinary CI and actual deployment acceptance are separate. This does not verify a company identity provider, storage root, server installation, real file, scanner or deployed Worker/API route. Runtime configuration and real deployment remain outside this package. Historical e2038a94/schema0030 images remain unchanged and are not covered by the current source's Next 16.4.5 security patch; the earlier Node five-second harness timeout root cause remains unknown.

Runtime reference: [Cloudflare Request body length and redirect behavior](https://developers.cloudflare.com/workers/runtime-apis/request/). The test uses the locked Miniflare API and its supported explicit cf/outbound settings; no dependency or production compatibility setting changes.
