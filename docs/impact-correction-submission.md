# Impact SUPERSEDE controlled submission

Updated: 2026-10-10 (Asia/Shanghai). Codex / Work. Approved slice A only; no independent paid API worker or local Plus CLI was launched.

## Scope and frozen request

The existing backend supersession is reused. No backend/schema/migration change: API0.18.40/schema0022, 69 pages and fourteen business-command routes remain unchanged. Withdrawal, bilingual correction UI and manual export/import are subsequent slices; ordinary ASSESS remains a separate protocol.

The envelope has exactly operation=impact-correction, target=Issue number, body and predecessor. Body fields are request_id, actor_name, reason, release_id, snapshot_id, decision, explicit nullable evidence_ref, supersedes_id and correction_reason.
Predecessor fields are id, release_id, snapshot_id and decision. Its ID/context must match the body; the new request ID differs from the predecessor. Decisions use only AFFECTED/NOT_AFFECTED/NEEDS_REVIEW. Neither WITHDRAW nor WITHDRAWN is accepted. Predecessor review metadata is not sent as an additional backend field.

Ordinary preparation normalizes target, body UUIDs, declaration, reason and nullable reference. Predecessor/supersedes UUIDs must be canonical lower-case. correction_reason is nonblank, trimmed and limited to4000 characters separately from reason. Invalid Unicode surrogates, unknown fields, caller URL/header/credentials and malformed context are rejected. The complete canonical command is limited to8192 UTF-8 bytes; individually valid reasons still must fit the combined byte limit. Reply JSON is bounded to16384 bytes.

The backend remains authoritative for current-effective predecessor, exact Issue/Release/FROZEN Snapshot, REVIEWER project/software scope or PLATFORM_ADMIN exception, Issue serialization and atomic write/audit commit. No current state is inferred from caller predecessor text.

## Independent server gate and private session

POST-only /auth/impact-correction and /auth/impact-correction-receipt require:
- IMPACT_CORRECTION_SUBMISSION_MODE=enabled
- IMPACT_CORRECTION_APPROVED_API_BASE_URL exactly matches the approved configured API.
- IMPACT_CORRECTION_APPROVED_APP_ORIGIN exactly matches the configured application origin.

The sample is disabled; absent/invalid values and ordinary Evidence, Acceptance correction, unrelated or NEXT_PUBLIC gates do not enable it. Valid OIDC code-flow/encrypted-session configuration, same-origin/Fetch-Site, JSON-only streaming limit, unique cookie and current token-bound USER are rechecked. Current read-only mode denies business POST but permits own original-audit recovery. The proxy sanitizes denial details and keeps responses private/no-store; credentials remain server-only.

The session executor lazily imports only the new protocol modules. Existing session tests and protocol assertions are unchanged; no generic URL forwarding or broader command gate is introduced.

## Exact original audit and receipt

Submission uses only /api/v1/issues/{encoded Issue number}/impact-assessments. BackendHTTP200/201 then requires the original EVT-IMPACT-{request_id} audit. Recovery performs only the audit GET and never a business POST or current-object query.

The audit must match its event ID/number, current authenticated principal, declared actor, original reason, ISSUE_IMPACT/Issue/SUPERSEDE, Issue UUID/reference, assessment ID, Release/Snapshot, new decision, predecessor ID, previous decision, correction_reason, AUTHENTICATED_PRINCIPAL source and version1 SHA256 of the canonical JSON nullable evidence_ref. An ordinary ASSESS event cannot confirm this receipt. Missing legacy digest, altered/null reference evidence or incomplete predecessor payload remain unknown.

The audit's historical snapshot_no is retained; no caller-supplied/current label is substituted. Receipt fields whitelist only original request values, previous_decision, Issue ID/reference and original snapshot label. Current status, successor/effectiveness, readiness/replayed flags and extra secrets are omitted. A receipt confirms the original supersession; it does not claim the judgment remains current or a release is approved.

## Controller and unknown outcomes

The controller accepts only an exact boolean-confirmed canonical review and deeply freezes the original command/bytes. Sending/checking synchronously interlock; confirmed is terminal. Lost, malformed, oversized, inaccessible, unexpected-status or mismatched responses remain outcome_unknown. Missing audit does not prove absence. Recovery or an uncertain write retains unknown across later denial or disabled gates. Explicit retries preserve the exact original request ID/bytes; there is no automatic retry, current-state fallback, local/session storage or export/import.

Regression files: frontend/tests/impact-correction-transport.test.cjs and frontend/tests/impact-correction-proxy.test.cjs, with actual OIDC login/session mocks and independent scoped fixtures. They cover all decisions, exact predecessor/actor/body/audit binding, nullable and Unicode evidence digests, normalization/byte bounds, frozen retries/interlock/terminal state, unknown retention, CSRF/current USER/duplicate cookie, independent gates and private error mapping. frontend/scripts/check-browser-auth.cjs checks both actual Next routes under disabled configuration, plus bilingual SSR. Mock/HTTP/SSR is not actual browser/provider acceptance.

Next B: bilingual predecessor-bound confirmation/results and strict manual export/audit-only import recovery. C withdrawal model/migration is separately reviewed, including no resurrection of older independent judgments. Review/downstream policies, actual identity/environment acceptance and offline operations remain pending; VIN last.

