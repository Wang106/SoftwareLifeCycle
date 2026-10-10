# Acceptance correction manual recovery

This package completes the second enabled task after the separate correction confirmation/result UI. Public submission remains disabled; API 0.18.40, schema 0022 and all command counts are unchanged.

## Canonical export

A confirmed correction can be manually copied as `slc-acceptance-correction-recovery` version 1. The envelope binds the exact application origin, operation, SCR target, original canonical body and predecessor review context. It includes the original request UUID, declaration, reason, criterion, selected DVP, SUPERSEDE/WITHDRAW action, predecessor UUID, original DVP and original action. It contains business data: store it securely. It is not evidence of execution or an authenticated identity.

The original frozen command must round-trip canonically, and only boolean-confirmed reviews export. There are no credentials, principal assertions, server URLs, receipts, current-effectiveness or success claims. No automatic export or browser storage is added. The pretty envelope is visible for manual copying when the clipboard fails.

## Same-site read-only import

Open the correction panel from history, or use `/commands?correction_action=SUPERSEDE` in a new session. Paste text into the correction recovery field and explicitly import. No network call occurs. An in-memory facade is staged as `unknown` and has no `send` method; the UI hides submission and retry even when that environment otherwise supports writes. An already prepared/attempted request cannot be replaced by an import. Changes to unsent import text invalidate captured import handlers.

The format/version/field set, original body and predecessor are strict. Only the exact compact or pretty canonical representation (with optional outer whitespace) is accepted. Duplicate keys at any depth, reordering/normalization, other command formats, extra credentials/result fields, mismatched predecessor/action/criterion, invalid Unicode, invalid UUID, excessive body/UTF-8 length, and a different origin are rejected. Envelope maximum is 32768 UTF-8 bytes; command maximum remains 8192. HTTPS origins or exact local-loopback HTTP origins are allowed; path, trailing slash, credentials and remote HTTP origins are not.

Import is not permission. Explicit recovery uses the existing independent receipt proxy with the current unique token-bound USER session. That proxy reads only the original atomic audit; it does not reissue a business write. The audit must bind original actor, full request and predecessor. Missing/denied/malformed evidence remains unknown and cannot unlock a new request. Recovery can continue in read-only mode. A matching original receipt is terminal; only then may the user start a new preparation.

Manual export, send and recovery retain synchronous locks. Original body bytes and request ID survive export/import into a new component. A copied request alone is not the recovery envelope. Every new mounted component starts with no imported request, and there is no automatic query/retry/storage.

## Verification and remaining limits

13 new format/controller/component-event and bilingual SSR regressions cover both actions, zero-network import, missing/denied original audit, facade without send, exact original bytes across new components, terminal confirmation, session capability refresh, concurrent queries, stale import handlers, Unicode/shape/origin/duplicate-key attacks and clipboard fallback. Existing 18 correction UI regressions remain unchanged.

These tests simulate unload/session replacement; actual approved-provider/browser/multi-user cross-session acceptance is still pending. beforeunload warnings do not guarantee in-app navigation protection. The internal server has not been deployed, OIDC is undecided, and no real identities/grants/provider secrets/writes are configured. Progress remains 36/44=82% pending those acceptance gates. Actions deploy is independently gated; Cloudflare provider checks and Render live API/schema require separate evidence.

The two enabled UI scopes are implemented. Impact withdrawal/submission, review/downstream correction and offline operations scopes remain disabled pending a concrete reviewed package; VIN stays last.
