# Impact withdrawal controlled UI and recovery

This package adds the browser protocol for the existing append-only Impact withdrawal backend. It does not change schema `0024_release_customer_scope`, API `0.18.43`, Seed data, or the ordinary Impact assessment and `SUPERSEDE` protocols.

`impact-withdrawal` is a separate canonical command. Its body contains only `request_id`, declared `actor_name`, `reason`, exact Release and frozen Snapshot UUIDs, `supersedes_id`, and `correction_reason`. The predecessor review records the exact predecessor UUID and technical decision. A withdrawal has no replacement `decision` or `evidence_ref`: it is not `NOT_AFFECTED`, does not revive an older independent judgment, and grants no release permission.

The two Node routes `/auth/impact-withdrawal` and `/auth/impact-withdrawal-receipt` use an independent, default-disabled gate:

- `IMPACT_WITHDRAWAL_SUBMISSION_MODE=enabled`
- `IMPACT_WITHDRAWAL_APPROVED_API_BASE_URL` exactly matches the authenticated server API base
- `IMPACT_WITHDRAWAL_APPROVED_APP_ORIGIN` exactly matches the encrypted session origin

The proxy rechecks one current token-bound `USER`. Read-only mode denies the business POST but still permits the signed-in user to query their matching original audit. It never accepts caller URLs, headers, credentials, ordinary assessment bodies, or `SUPERSEDE` envelopes. Backend denial details are reduced to bounded public error codes.

Successful HTTP 200/201 from the write is not proof. Confirmation requires the exact `EVT-IMPACT-{request_id}` audit and binds the authenticated principal, declared actor, Issue, Release, Snapshot, predecessor, original technical decision, both reasons, `WITHDRAW`, context sequence, explicit null decision/evidence/after-withdrawal relation, snapshot number, and the versioned digest of null evidence. Current context status, later judgments and write-response observations are excluded.

The browser freezes the original bytes and request ID. Lost results remain `unknown`; only an explicit retry resends the same bytes. Audit recovery only performs GET. Concurrent send/query/retry actions interlock, and later denials cannot erase an earlier uncertain result.

Manual export uses `slc-impact-withdrawal-recovery`, version 1, bound to the exact site origin. Import is canonical, zero-network and exposes no send method. The imported UI remains audit-query-only even if submission is otherwise enabled. The text contains business data and is not execution evidence.

The history entry offers separate replacement and withdrawal preparation links only for a canonical current terminal judgment. The API remains authoritative for current-predecessor, frozen-context and permission checks. Public demonstration stays read-only; no identity, grant, provider secret or write gate is enabled by this package.

Regression evidence covers the three predecessor decisions, strict command separation, original-audit binding, lost response and exact retries, same-site export/import, zero-network import, read-only recovery, independent gates, token-bound user checks, sanitized conflicts, bilingual UI, invalid contexts, production SSR, and disabled route behavior. These tests are protocol/SSR evidence, not real provider or multi-user browser acceptance.
