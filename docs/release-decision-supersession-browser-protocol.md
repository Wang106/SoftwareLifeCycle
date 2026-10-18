# Release decision supersession browser protocol

This package adds a browser preparation, confirmation, submission and original-audit recovery protocol for the append-only `ReleaseDecision` replacement contract. It does not enable a production write path by default and does not change the backend contract introduced by schema revision `0025_release_decision_supersession`.

## Independent default-off gate

All three values must exactly match before the page resolves a session or enables recovery:

- `RELEASE_DECISION_SUPERSESSION_SUBMISSION_MODE=enabled`
- `RELEASE_DECISION_SUPERSESSION_APPROVED_API_BASE_URL` equals the configured private API base URL
- `RELEASE_DECISION_SUPERSESSION_APPROVED_APP_ORIGIN` equals the configured application origin

Submission additionally requires an authenticated non-read-only session. Recovery may use an authenticated read-only session because it performs only an original-audit `GET`. Public/demo deployments remain disabled unless an operator explicitly supplies the independent approved values.

## Frozen request

The browser freezes one canonical request containing:

- a new approved request number and new request UUID;
- the exact predecessor decision UUID, decision number, decision and readiness declaration;
- the predecessor release UUID and frozen snapshot UUID;
- the complete new decision, declared authority text, readiness declaration, optional notes and correction reason.

The proxy accepts only same-origin JSON `POST` requests up to 8192 bytes. It forwards only the backend request body to `POST /api/v1/approvals/{approval_no}/release-decision`; predecessor context is retained for client-side and receipt verification and is never forwarded as an extra backend field.

## Outcome and recovery

A successful backend response is not displayed as proof. The proxy reads `GET /api/v1/activity/EVT-RD-{request_id_without_hyphens}` and accepts a receipt only when the authenticated principal, action `DECISION_SUPERSEDED`, entity, new approval, release, frozen snapshot, predecessor, complete original request and applied result all match.

Transport failure makes the outcome unknown and locks the frozen request. The recovery action queries only that original audit and never resubmits the business write. A later disabled, rejected or conflicting attempt cannot downgrade an earlier unknown outcome to a safe-to-retry rejection.

This confirmation changes only future effective-decision reads. It does not edit the predecessor, revoke an earlier delivery or production fact, prove a physical rollback, enable OIDC, or constitute production acceptance.
