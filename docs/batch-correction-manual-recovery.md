# Batch correction: manual cross-session original-audit recovery

## Scope and trust boundary

The existing Batch workbench retained an uncertain attempt only in page memory. This
package adds an explicit manual export/import path, following the existing acceptance
correction recovery design. It does not add business submission routes or enable any
provider, identity or write configuration.

An export contains the frozen, explicitly confirmed original request, its exact target,
private preparation context, origin, format and version. Confirmation means the operator
confirmed the request, not that execution succeeded. Unknown attempts can be exported.
The text contains business metadata and must be stored securely by the operator; it is
not proof, a credential, an authorization grant or a current-state snapshot. No cookie,
access token, principal/session assertion, receipt or success flag is exported.

Import validates the bounded canonical envelope and exact original command. It performs
zero network calls and stages an unknown result. The imported facade exposes only the
original-audit query, not send/retry. The UI checks the current page target, preserves
frozen original context and never automatically queries, refreshes private context or
submits a replacement. No localStorage, sessionStorage or automatic persistence is used.

The operator explicitly queries after signing in. The existing receipt proxy revalidates
the current token-bound USER/session and reads the original audit; it never writes or
uses current mutable history to infer success. The audit must match current actor,
original request, exact parent/Batch, before context and after values. A different actor,
revoked session, altered payload, missing original audit or historical missing parent
binding cannot become a confirmed receipt. A valid new session for the same original
actor can query; former write scope is not reinstated by importing metadata.

Default-off capability gates remain unchanged. Read-only original-audit recovery is not
new permission to write. Confirmed receipts describe the original historical correction,
not current facts, physical production actions or present authorization.

## Validation and remaining acceptance

New protocol, actual UI interaction and synthetic current-session proxy integration tests
exercise manual export/import, unknown outcomes, strict validation, original byte binding,
no implicit network/business writes, explicit query and capability/target changes. Existing
Batch transport/proxy and localization suites remain unchanged. Exact results and reviewed
commit/CI/artifact/provider evidence are recorded in HANDOFF and the final PR comment.

Local validation:20 new cases, full frontend1721 passed0skip, independent54 scoped
cases passed, typecheck/Worker configuration/Next build and52automation passed. The
notified origin assertion repair changed only new tests; parser/business gates unchanged.

All local fixtures are synthetic. Public403/browser restrictions are not bypassed; this is
not real OIDC, live multi-user browser or company-server acceptance. Completion remains
36/44=82% until milestone-level external evidence exists. Next bounded work in the approved
finite sequence is equivalent Changeover manual recovery, then administrator-registration
manual recovery, followed by integration review; no open-ended feature queue is implied.
