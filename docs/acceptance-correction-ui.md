# Acceptance relationship correction interface

The first enabled UI task now connects PR43's existing correction controller and independent proxy to `/commands` from effective acceptance assignment history. A correction context (`predecessor` or `correction_action`) loads the separate panel; ordinary ASSIGN remains its own workbench and transport. The API/schema remain 0.18.40/0022, with 14 business commands.

## Review and original results

Only explicitly effective ASSIGN/SUPERSEDE history rows offer replacement and withdrawal preparation. Links bind the SCR, criterion, predecessor UUID, original DVP UUID and predecessor action. Query context is bounded and untrusted: canonical parser validation and the backend's effectiveness/scope/concurrency checks remain authoritative. Direct preparation is possible via `/commands?correction_action=SUPERSEDE`; no real identity, permissions or configuration are obtained from URL parameters.

A new request UUID is generated when preparing. The bilingual review shows the exact SCR, criterion, predecessor/action, selected DVP, declaration, reason and request ID. SUPERSEDE requires a different DVP; WITHDRAW retains the predecessor DVP. Explicit confirmation freezes the canonical envelope. Editing or changing unsent query context invalidates confirmation; stale handlers cannot send. Once attempted, an in-memory controller retains its original bytes across panel context/capability refreshes.

The server independently checks ACCEPTANCE_CORRECTION approved bindings, resolves exactly one current secure session, and passes only submission/recovery booleans. Submission requires read_only_mode exactly false; recovery can query the signed-in user's original audit after a read-only transition. The public configuration remains disabled.

Sending, querying and copying interlock synchronously. Explicit retries use the original body and request ID. No automatic retry is added. Unknown remains frozen even after a later rejection; only confirmation or an initial explicit rejection permits starting a new request. beforeunload warns during sending/checking/unknown; it does not guarantee protection against in-app navigation or component unmounting.

The result displays only the original matching audit receipt, not current coverage/effectiveness or replay inference. Independent links open the exact SCR criterion view, original audit, predecessor audit and original/replacement DVP in new tabs. Original values remain inert text; provider messages and credentials are not rendered.

## Verification and limits

18 new compiled component-event/server-page/history-link and bilingual SSR regressions cover both actions, exact original receipts, stale confirmation/context/capability handlers, double clicks, copy/send/query locks, lost responses, original-byte retries, read-only recovery, current-session uniqueness and invalid/oversized input. These mocks and SSR checks are not actual provider/browser/multi-user acceptance.

Recovery is memory-only in this package. Copying the confirmed request does not produce an importable recovery export. Reload/unmount loses the controller; manual same-site recovery export and audit-only import are the next enabled task. No local/session storage, credentials, OIDC provider, real submissions, deployments or internal-server installation are enabled by this interface.
