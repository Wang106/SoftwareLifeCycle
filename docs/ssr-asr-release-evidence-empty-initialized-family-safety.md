# SSR/ASR release-evidence empty initialized-family safety

## Scope

The read-only `/demo/releases` page distinguishes an unavailable evidence API,
an explicitly uninstalled sample family, and an initialized sample family. The
demonstration envelope carries both an `initialized` flag and its bounded
`items` collection.

This package completes the envelope consistency check: an initialized response
must contain at least one fully parsed evidence row. It complements the existing
rule that an uninitialized response must contain no rows.

## Fail-closed contract

- `sample_only: true`, `initialized: false`, and `items: []` remains the valid
  “evidence samples not installed” response.
- `sample_only: true`, `initialized: true`, and a non-empty, valid bounded row
  collection continues through the existing Snapshot, Readiness, Approval,
  Decision, identity, and confirmation checks.
- `sample_only: true`, `initialized: true`, and `items: []` is contradictory and
  makes the complete response unavailable.

The frontend does not render a blank successful page, reinterpret an empty
initialized response as an uninstalled family, invent evidence rows, or confirm
a formal release.

## Verification

The server-rendered demonstration regression suite covers all three envelope
states. The new case injects an initialized empty collection and requires the
existing API-unavailable state, with neither the uninstalled-family message nor
a formal-release statement.

## Safety boundary

This is defensive parsing for one synthetic read-only response. It does not
change the backend, database, Seed data, identities, approvals, write gates, CI,
or deployment configuration. A non-empty response still does not establish
real approval authority, Snapshot provenance, production readiness, or formal
release.
