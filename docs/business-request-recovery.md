# Original business request recovery

`/commands` supports manual recovery export and audit-only import for all fourteen
business commands. This is not an identity/admin import, a signed receipt, automatic
storage, a file upload or permission to enable public writes.

## Export and import

After confirming an original request, use **Copy original recovery text**, or expand
the manual-copy text. Save it securely before leaving. The format is
`slc-business-recovery`, version `1`, with exact origin, operation, target and original
canonical body. No credential, authenticated identity or claimed receipt is exported.
Business declarations, comments, evidence references and private resource paths can
be present: copying is an explicit user action, not anonymization or encryption.

In a later session on the same origin, paste the text into **Restore an original
business request** and explicitly stage it for audit query only. Staging performs
zero network requests and marks the outcome unknown. Then explicitly query the
original audit through the command's independent recovery gate and current signed-in
USER session. Read-only sessions can query; wrong principal, missing/mismatched audit
or later denial stays unknown. No current-object or POST-result fallback proves the
original operation. Confirmed original values and their detail/audit links use the
existing exact receipt validators.

Imported recovery has no `send` method and the workbench hides all write/retry
buttons for it. Even if a write gate is enabled later, the imported request remains
query-only. A confirmed result permits starting a separate new request. An unknown
import cannot replace an existing request or silently become a new one. Original
in-page controllers still support their existing explicit exact-byte retries; this
does not extend that capability to imported text.

## Validation and limitations

Accept only exact compact JSON or the exact two-space JSON exported by this format,
with optional surrounding whitespace. The version/fields/origin, supported command,
all body fields and existing 8192-byte command transport limits are revalidated.
Total recovery input is capped at 32768 UTF-8 bytes; unpaired surrogates are rejected.
Canonical equality rejects duplicate JSON keys, altered numeric encodings, reordered
keys, normalized-away whitespace/case, extra URLs/headers/credentials or a purported
receipt. Nulls, original IDs, ordered artifact sets and original timestamps are kept.
Changing a body into another structurally valid original request does not prove its
authenticity: only server-side original actor-bound atomic audit can confirm it.

HTTPS origins and explicit loopback HTTP development origins are supported. Origin
binding is an accidental cross-site guard, not a signature or proof that the backend
behind that origin has not changed. No backend URL, authorization or identity is
trusted from the text. No URL or resource path inside it is fetched.

There is no automatic clipboard read, file download/upload, localStorage/sessionStorage,
IndexedDB, credential export, background query or automatic write. Only the user's
manually saved recovery text survives reload/unmount; unsaved page state still does
not. The old `{method,path,body}` API instruction export is not a recovery artifact.
Real provider/browser/internal deployment acceptance remains pending. Public sample
stays read-only, OIDC and all write gates stay disabled. API0.18.38/schema0020 unchanged.
