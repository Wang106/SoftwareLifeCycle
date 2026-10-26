# Controlled Changeover correction workbench

## Scope and acceptance boundary

Baseline main `88adbce7996c6430b2728b1cdaea8f4331dd7fe6` (PR155) includes the
controlled Batch correction slice, but Changeover still has only a correction command
and sample history. This package adds the missing private preparation context and
independently default-disabled bilingual correction/review/confirmation/original-result
recovery experience. It is a Changeover-only increment, not a new generic parser package.

This advances R12/R13 and the implementation portion of `correction-e2e`. Approved
provider, real browser, multi-user and downstream acceptance remain separate. No real
identities, writes, provider configuration, credentials, migrations, CI or permissions
are changed. Overall36/44=82% and existing seven module/plan percentages stay unchanged
unless complete milestone evidence—not merely this implementation—supports a change.

## Changeover-specific semantics

The recorded target `to_release_id` is immutable. The replacement source release must
be a valid UUID and differ from the target; backend existence and authorization checks
remain authoritative. Unlike Batch correction, the existing Changeover command interprets
null `changed_at` as server current time. This browser workflow therefore requires an
explicit timestamp, freezes it before submission and preserves its normalized UTC
microseconds on every explicit retry. It never silently submits null or changes the
existing backend command's semantics. Null note clears the note.

The private context is a coherent read-only observation, not a reservation or grant.
Current ACTIVE identity/session and exact deployment role are revalidated; public
sample history never authorizes writes. The command separately validates current
permissions and revision/predecessor before any new correction. Revoked sessions or
roles do not become valid because an old form or request ID exists.

## Original evidence, not current-state inference

NEW Changeover correction audit events include the canonical locked deployment number
outside the existing request fingerprint. Historical append-only audit events and
idempotent replay remain unchanged. A browser receipt must match exact current actor,
parent, child, frozen request and original before/after values. Missing historical
parent binding stays UNKNOWN/manual review; it is not silently upgraded or rewritten.

An uncertain result retains the original request ID and bytes. Recovery reads only
that original audit; explicit retry sends only that original command. Later current
history, HTTP success alone or a new revision is not proof of the original operation.
Stale known rejection requires fresh preparation and explicit review, never automatic
rebase. No automatic retry or background business write is introduced.

## Verification and remaining work

Focused semantic, private-session/scope, original-audit, frozen-UI and offline disabled
inventory tests plus full exact-head CI are required. Fresh main CI/artifacts and
Cloudflare/Render evidence are tracked separately after protected merge. SSR tests do
not substitute for real browser acceptance; existing sandbox/browser restrictions are
not bypassed. Final exact evidence belongs in the PR closure and repository handoff.

Even after Batch and Changeover code slices, remaining real-provider login/session,
administrator, genuine multi-user commands/corrections and company operations require
an approved target, credentials operated by the user, acceptance owners and policies.
Those are external acceptance gates, not an invitation to invent further tiny code
packages or inflate completion percentages.

Local verification: 107 related backend cases pass (97 realPG deselected locally);
44 new backend cases comprise21 SQLite and23 realPG variants. Full frontend1,672
passes with zero skips, including36 new tests; UI/i18n151, typecheck, Worker config,
Next build,52 automation and15 offline preflight checks pass. A new timezone test
initially exposed SQLite fixture offset loss; the shared fixture now uses equivalent
UTC and a dedicated PostgreSQL test retains non-UTC roundtrip coverage. No existing
service semantics/assertions or test gate was weakened. RealPG acceptance awaits CI.
