# SSR/ASR release evidence collection identity safety

## Scope

The read-only `/demo/releases` page consumes a bounded synthetic SSR/ASR evidence family. Each rendered release panel is keyed and linked by `release_id`, while each DVP link inside a panel is keyed and linked by its DVP `id`.

The shared runtime parser now requires these identities to be unique in their own collections:

- every initialized demonstration row has a distinct `release_id`;
- every `dvp_items` entry within one row has a distinct `id`.

If either identity is repeated, the complete demonstration response is rejected. The page shows the existing evidence-unavailable state and does not render either conflicting row or link. No field is selected as the winner and no formal-release conclusion is inferred.

## Preserved behavior

- Distinct releases may reference the same DVP identity because each release panel supplies its own release and Snapshot query context.
- DVP labels are display text and are not used as identity; different IDs may retain the same recorded label.
- The existing 200-row bounds, text limits, coverage invariants, Readiness rule identity checks, and formal-release confirmation rules remain unchanged.
- The uninitialized sample-family response remains valid only with an empty projected item list.

## Safety boundary

This change only validates the frontend read model. It does not change the API, backend, database, Seed, identities, approvals, write gates, CI, or provider configuration. A valid synthetic response remains demonstration evidence and does not prove a real approval, current authorization, frozen production Snapshot, or formal release.

## Verification

`frontend/tests/release-demo-evidence.test.cjs` covers conflicting duplicate release rows and conflicting duplicate DVP links. Both cases must render the unavailable state without leaking either conflicting proof. The full frontend suite and production build remain the broader regression gate.
