# Changeover correction: manual original-audit recovery

This is the second package in the finite server-independent Batch, Changeover and
administrator-registration recovery sequence. It fills the Changeover workbench's
page-memory-only gap without changing backend or live configuration.

## Frozen evidence, not authorization

The explicitly confirmed original request/context can be manually exported even when
its outcome is unknown. Confirmation means request review, not execution success.
The canonical bounded envelope binds this site origin, format/version, exact deployment
and Changeover, original context, revision/predecessor/request ID and replacement body.

Changeover semantics are preserved: body occurrence time is explicit and frozen, never
regenerated from a clock or refreshed context; source release is required and distinct
from immutable target release. A historical null occurrence time in the original context
remains null while the replacement body requires its original explicit time. Canonical
transport values retain their original instant and bytes; imports cannot silently
normalize noncanonical timestamp spellings. Batch envelopes are not interchangeable.

Import validates metadata but does not trust it as evidence of execution or permission.
It performs no network activity and stages an unknown outcome in an audit-only facade
with no send/retry method. The UI checks the current route target, labels imported context
unverified and requires a separate explicit query. Current authenticated USER/session and
original actor/parent/target/request/before/after are checked by the unchanged receipt proxy.
Fresh valid sessions for the original actor can recover the original receipt; a foreign
actor, revoked session, tampered source/target/time/body or old missing-parent audit cannot
become confirmed. Current mutable history is never used to infer original success.

Manual text contains business metadata; the operator must store it securely. It excludes
credentials, tokens, principal/session claims, receipts and success flags. No browser
storage or automatic persistence/query/submission is added. Clipboard copy is explicit,
with displayed canonical text fallback. Default-off settings and existing business APIs,
authentication, CI, provider settings and permissions remain unchanged.

## Acceptance boundaries

Synthetic protocol, actual UI interaction and composed real-proxy fixture tests cover
unknown export, fresh-instance import, strict limits/canonicality/origin/cross-kind checks,
explicit original-audit reads only, capability/route races and Changeover-specific source,
immutable target and occurrence-time binding. Existing tests remain intact. Final local,
independent-review and exact PR/main CI/artifact/provider results are recorded in HANDOFF
and the final PR comment. No public403 or browser restriction is bypassed.

Local results:23new cases; fullfrontend1744 passed0skip; independent59focused passed;
typecheck, Worker configuration, production build and52automation passed. No tests or
gates were weakened.

This is implementation acceptance, not actual provider/OIDC/live browser/multi-user or
company-server acceptance. Overall36/44=82% remains unchanged. After this package closes,
only administrator-registration manual recovery and the finite integration review remain
in this requested server-independent sequence; no open-ended feature queue is implied.
