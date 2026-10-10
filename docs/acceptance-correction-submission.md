# Acceptance correction controlled submission protocol

Implemented: transport/controller and independent server proxy foundation. Bilingual correction confirmation/result UI, manual export/import recovery and real-provider acceptance remain pending. Ordinary ASSIGN remains a separate protocol. Backend API 0.18.40, schema 0022 and 14 business-command count are unchanged.

## Frozen command

The exact envelope contains only `operation: "acceptance-correction"`, `target` (SCR number), `body` and `predecessor`.
The backend body contains request_id, actor_name (declaration), reason, criterion_id, dvp_item_id, action (SUPERSEDE or WITHDRAW) and supersedes_id.
Predecessor review context contains id, criterion_id, dvp_item_id and action (ASSIGN or SUPERSEDE); it is not sent as extra backend fields.

A fresh request ID must differ from the predecessor. The predecessor ID and criterion must match supersedes_id and criterion_id. SUPERSEDE selects a different DVP item; WITHDRAW retains the predecessor DVP item. Predecessor IDs use canonical lower-case UUIDs; ordinary preparation normalizes body UUIDs, declared text and target. Unknown fields, ASSIGN, ended predecessor action, caller URL/credentials, unpaired surrogates and requests exceeding 8192 UTF-8 bytes are rejected. The backend remains authoritative for current effectiveness, project authorization and concurrency.

## Independent gate and session

Both POST-only routes `/auth/acceptance-correction` and `/auth/acceptance-correction-receipt` require all three server-only bindings:
- ACCEPTANCE_CORRECTION_SUBMISSION_MODE=enabled
- ACCEPTANCE_CORRECTION_APPROVED_API_BASE_URL exactly matches the configured approved HTTPS API.
- ACCEPTANCE_CORRECTION_APPROVED_APP_ORIGIN exactly matches the configured application origin.

The example remains disabled; absent, invalid or unrelated/public gate values cannot enable it. Existing OIDC/encrypted-session configuration, same-origin/Fetch-Site checks, JSON-only streaming limit, unique secure cookie and current token-bound USER validation apply. Responses remain private/no-store and do not expose backend detail or credentials. Read-only mode denies submission while allowing own original-audit recovery. Neither route provisions accounts, grants, keys or secrets.

## Original audit receipt

Submit writes only to the existing fixed SCR acceptance-dvp-links endpoint, then reads EVT-AC-{request_id} after backend HTTP 200/201. Recovery reads only that original audit and performs no business POST. It never queries the current relation, criterion coverage or latest status to infer success.

The original audit must bind authenticated current principal, declared actor, reason, SCR identity/reference, ACCEPTANCE_DVP/SoftwareChangeRequest, exact SUPERSEDE/WITHDRAW action, assignment/criterion/DVP IDs, supersedes_id, previous_dvp_item_id and previous_action. The receipt exposes only those original values and exact SCR ID/reference. Current successor, effective status, replay flags and extra secrets are omitted. An ordinary ASSIGN audit cannot confirm a correction, and correction evidence cannot confirm ordinary ASSIGN.

A lost/wrong-status write response or inaccessible/missing/malformed/oversized/mismatched original audit leaves outcome_unknown. Audit absence does not prove a write never committed. Explicit retries preserve the exact original frozen bytes and request ID; no automatic retry occurs.

## Memory controller and verification

Confirmation must be exact boolean true for a canonical deeply frozen envelope. Sending/checking interlock synchronously; confirmed is terminal. Recovery or an uncertain write preserves unknown across subsequent denial or gate/session changes. No local/session storage, automatic export/import or network activity is added.

Regression files: frontend/tests/acceptance-correction-transport.test.cjs and frontend/tests/acceptance-correction-proxy.test.cjs. They cover both actions, predecessor and actor/audit bindings, byte preservation, concurrency interlock, unknown retention, independent gates, CSRF, streaming limits, current USER checks, ambiguous cookie rejection and private error mapping. frontend/scripts/check-browser-auth.cjs exercises both real Next routes under disabled configuration and bilingual SSR. These mocks/HTTP/SSR checks do not replace actual approved-provider/browser/multi-user acceptance.

Next package: bilingual predecessor-bound confirmation, original-result display and strict manual export/audit-only import recovery. Then Impact correction/withdrawal, release-review/downstream policies and approved environment/offline operations acceptance; VIN last.

