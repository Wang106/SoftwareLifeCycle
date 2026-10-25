# SSR/ASR release-evidence initialization consistency safety

## Scope

The read-only `/demo/releases` page distinguishes an unavailable evidence API
from a valid sample family that has not been installed. The demonstration
envelope carries both an `initialized` flag and its bounded `items` collection.

This package makes those two fields consistent: an explicitly uninitialized
response is valid only when `items` is empty.

## Fail-closed contract

`sample_only: true` with `initialized: false` and `items: []` continues to render
the existing “evidence samples not installed” state.

If `initialized` is false while one or more evidence rows are present, the
complete response is rejected as unavailable. The frontend does not discard the
rows and relabel the contradictory response as a normal uninstalled state, does
not expose links from those rows, and does not infer formal release evidence.

Initialized responses retain the existing bounded row parsing, identity,
Snapshot, Readiness, Approval, Decision, and confirmation checks.

## Verification

The server-rendered demonstration regression suite keeps an empty
uninitialized response valid and injects a contradictory uninitialized response
containing an otherwise valid evidence row. The latter must render the existing
API-unavailable state without Approval or Decision links.

## Safety boundary

This is defensive parsing for one synthetic, read-only response. It does not
change the backend, database, Seed data, identity, credentials, command gates,
CI, or deployment configuration. It does not establish real approval authority,
Snapshot provenance, production readiness, or formal release.
