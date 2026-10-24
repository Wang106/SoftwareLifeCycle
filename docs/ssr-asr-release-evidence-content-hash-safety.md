# SSR/ASR release evidence content-hash safety

## Scope

The SSR/ASR release detail and demonstration pages consume a snapshot `content_hash` as part of a read-only evidence chain. The snapshot service creates this value with `hashlib.sha256(...).hexdigest()`, so the canonical wire form is exactly 64 lowercase hexadecimal characters.

This package makes that existing producer contract explicit at the shared frontend parser boundary. It does not change the API, database, snapshot calculation, release decision rules, identity, or write controls.

## Fail-closed contract

A non-null snapshot is accepted only when `content_hash` matches `^[0-9a-f]{64}$`. A short or long value, a non-hexadecimal character, or uppercase text invalidates the complete containing response:

- an exact SSR/ASR evidence summary renders the existing unavailable state;
- the release-evidence demonstration renders the existing API-unavailable state;
- neither path renders approval or decision links from the malformed response;
- neither path confirms a formal release.

The frontend does not truncate, pad, lowercase, or otherwise repair the value. A valid 64-character lowercase SHA-256 value continues through the existing snapshot, readiness, approval, decision, and current-confirmation checks.

## Verification

The component-level SSR tests exercise the exact summary and demonstration consumers. They retain canonical hashes and reject 63-character, 65-character, non-hexadecimal, and uppercase values without throwing.

This is a client-side safety boundary for read-only evidence display. It does not attest that a valid-looking hash was calculated from the correct artifacts, and it does not turn approval or CI success into a formal release.
