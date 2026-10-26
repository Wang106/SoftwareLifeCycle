# Operational telemetry and incident evaluation

## Scope and acceptance contract

This package implements a missing part of Phase 7 / R15: structured request observations,
bounded metrics and offline alert evaluation, with incident response procedures. At baseline
`f4480489205b9e573a0ac4c7695ffdbb6ff0ec5a`, the API had `/health/live` and schema-aware
`/health/ready`, but no request telemetry middleware, metrics-window evaluator or incident
runbook. Existing health endpoints alone did not provide request error/duration evidence.

Acceptance for this **code package**:

1. Opt-in middleware observes successful, rejected, failed, interrupted and streamed requests
   without changing response messages, business audit events, auth/read-only behavior or exceptions.
2. Logs never include credentials, identity, peer IP, incoming request IDs, query strings,
   request/response bodies, raw paths or exception text. Route templates are fixed registered
   templates; unmatched/early-guard requests use one sentinel. No mutable per-route counter cache.
3. A bounded, explicit offline window computes reproducible metrics and reference alert states,
   rejects malformed/oversized/duplicate observations, never sends notifications, and does not
   turn missing data into health or complete-collection claims.
4. Tests exercise actual FastAPI/ASGI behavior through metrics evaluation, as well as direct
   streaming/cancellation/send/sink-failure paths. Existing full CI remains mandatory.

This is **not** production monitoring acceptance, a new authenticated service, or a company
installation. No changes to CI/scheduler/provider environment variables, credentials, log
collection, alert delivery, network, identities, migrations or public write gates are included.
The fixed roadmap and `ops-monitoring` milestone remain unchecked until the operational
acceptance below is satisfied. Do not start a chain of synthetic observability microtest PRs.

## Enablement and collection boundary

`REQUEST_TELEMETRY_ENABLED=false` is the default. Current deployments are not changed.
After separate operator approval, an isolated approved environment can set it to `true`
and restart its API using its existing process manager. This package does not perform that
step. The middleware adds no endpoint and no outgoing request. Its own logger
`slc.request_telemetry` writes one JSON object per line to stdout, without changing root or
Uvicorn logging; it does not rotate, delete, store or ship logs. A synchronous stdout sink can
add overhead or block when the deployment's logging pipe is blocked; target load/backpressure
validation is required before enabling in production. Normal sink exceptions are best-effort
and do not replace the original request exception. Loss of telemetry is possible.

**Only these new records have the content-free guarantee.** Existing reverse-proxy,
Uvicorn access/error and platform logs have separate policies and may contain raw URLs or
exception details; review them before collecting/exporting any real logs. This package does
not disable/reconfigure those logs. Never upload company logs to a public PR or cloud tool.

Only select this logger's own JSON records for the evaluator; mixed process stdout is not a
valid telemetry file. Use a locally controlled file with approved permissions. File retention,
rotation, encryption and authorized readers are operator decisions, not automatically changed.

## Record v1 and semantics

Fields: `schema_version=1`, `event=http_request`, integer UTC epoch `timestamp_ms`,
server-generated UUID-hex `request_id`, bounded `method`, `route`, observed `status`,
`outcome`, and `duration_ms`.

- The random ID is a **log-only observation ID**, not a client request identifier, business
  `request_id`, cross-service trace or audit correlation. It is never a metric label and is
  not accepted from headers, returned to clients, or added to domain writes.
- Route labels come from a snapshot of app route templates, never interpolated entity IDs.
  Early read-only/auth rejection before routing and unknown routes both use `__unmatched__`.
  These must not be interpreted as unknown endpoint counts or per-route authorization rates.
- Status `0` means this middleware has not observed a successfully sent response start.
  FastAPI's outer ServerErrorMiddleware may subsequently return 500. The telemetry is the
  outermost **user** middleware, not outside Starlette's error handling. A late failure can
  have status 200 with outcome `error`; do not infer success from status alone.
- `complete` means a final response-body message was sent and the ASGI invocation returned.
  `error`, `cancelled`, `disconnected`, `incomplete` are not successful completions.
  An observed disconnect after a complete body does not prove that the client failed to
  receive that body. No final client-delivery guarantee is made.
- Duration is monotonic elapsed time for the **whole ASGI invocation**, including background
  work after the response body. It is not browser latency, time-to-first-byte, network RTT,
  database latency or a production SLO. Timestamp is invocation start, not completion time.
- Process crashes or permanently hung requests may produce no record. Unsynchronized clocks,
  multiple workers, dropped logs and start-time window boundaries affect interpretation.

## Offline evaluation

From `backend`, using the project's installed requirements:

    python -m app.ops.telemetry_window own-synthetic-requests.jsonl --start-ms 1792980000000 --end-ms 1792980300000

The explicit half-open window is `[start_ms,end_ms)`, at most one hour. The evaluator reads
at most 100,000 lines of at most 2,048 bytes each; bounded memory holds at most 100,000 IDs
and durations. Oversized, malformed, non-finite, impossible field values and repeated IDs
inside the window fail with a fixed safe diagnostic and exit 2. No input file is modified.
Numeric duration input is limited to `0..2^53` milliseconds. Valid evaluation exits 0 even
when alert criteria trigger: this is evaluation, not a delivery command or health exit code.

Metrics: sample count, status-class/outcome counts, failed requests, failure ratio, nearest-rank
p95 invocation duration, and GET `/health/ready` observation/failure counts. A request fails
for this signal when status >=500 **or** outcome is not `complete`; expected 401/403/409 are
not automatically application failures. A readiness observation fails unless status200 and
complete. Readiness probes are included in the overall request metrics; account for their
traffic share when selecting actual operational SLOs.

Reference criteria (not approved SLOs):

| Signal | Minimum observations | Trigger |
|---|---|---|
| request_failures | 20 requests | Failure ratio >=5% |
| request_duration | 20 requests | p95 invocation duration >=1,000ms |
| readiness | One GET readiness observation | Any failed observation |

States are `triggered`, `clear`, or `insufficient_data`. No observations or missing readiness
produce insufficient data, not a green service. Every report includes
`coverage=input_only_not_proof_of_complete_collection` and `notifications_sent=false`.
Even `clear` only describes the supplied records: it does not prove that the entire service
was sampled, is currently healthy, or that alert delivery/acknowledgment works. Readiness
failure indicates unavailable DB/schema checks, not a reason to run a migration automatically.

## Incident handling

1. **Triage without mutation.** Record UTC window, exact deployed commit/provider deploy IDs,
   evaluator output and liveness/readiness observations from an authorized path. Check sample
   sufficiency and collection continuity first. Missing data is an observability incident,
   not successful health. Check whether an already running deployment explains the window.
2. **Classify.** Readiness503 with liveness200: inspect approved database connectivity/schema
   evidence. Invocation errors: compare exact commit and recent change with existing CI.
   High duration: distinguish whole-invocation/background work from client latency, inspect
   existing provider resource evidence. Repeated denies: investigate configuration/authorization
   without enabling writes or disclosing identities. None of these signals alone proves a cause.
3. **Contain safely.** Keep public read-only and all real write/identity gates unchanged.
   Escalate to the designated operator; do not grant roles, reset secrets, change networks,
   seed/migrate, automatically retry writes, restart production or roll back without approval.
   Preserve the exact checkpoint and trusted evidence; never attach request bodies/tokens.
4. **Recovery requires authorization.** If rollback is approved, use the separately verified
   deployment/rollback runbook and exact known-good release/schema compatibility. A passing
   request log is not a rollback test and not restoration proof. No generic rollback command
   is provided here because the production target has not been approved.
5. **Verify and close.** Confirm independent health, exact deployment, required functional
   smoke checks and an adequate post-recovery collection window. Record onset, impact,
   evidence, actions/approvals, recovery time, remaining unknowns and follow-up owner.
   Obtain human acceptance; never equate an alert acknowledgment with a formal release.

## Remaining operational acceptance

Before marking Phase7 monitoring complete: approve target/operator/on-call recipient and SLOs;
verify collection permissions, redaction across **all** log sources, retention and volume;
exercise request failure/readiness failure/slow invocation/log-loss conditions on that target;
verify notification delivery and acknowledgment with the approved recipient; rehearse authorized
containment/recovery and demonstrate return to baseline. No recipient, external alert system,
account credential, paid service or automatic remediation is selected or configured here.

Next candidate should be the approved target collection/delivery rehearsal (or another real
unfinished capability), not recursive docs-only updates. Docker image/actual offline deployment
remains separately blocked by an available authorized Docker build/test environment.
