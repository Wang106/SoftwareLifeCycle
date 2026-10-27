# Administrator registration: manual historical-audit recovery

This is the last implementation package in the requested finite server-independent
Batch, Changeover and administrator-registration manual-recovery sequence. It does
not deploy a company server, provision an identity, activate a grant or enable any
live write capability.

## Metadata and privacy

The existing registration preparation supports PRINCIPAL, GLOBAL, PROJECT and SOFTWARE.
A frozen confirmed request can be manually exported even when its original outcome is
unknown. Confirmation means request review, not execution success. The origin-bound,
versioned canonical envelope contains the original registration input and identifiers;
it is not a receipt or permission. It excludes issuer configuration, credentials, tokens,
actor/session assertions and success flags.

PRINCIPAL input necessarily includes the exact opaque provider subject, display name
and reason. These can be sensitive personal identifiers even though they are not login
credentials. The UI explicitly warns before revealing or copying recovery text; the
operator chooses secure local handling and must not share/upload it casually. No browser
storage, automatic persistence or automatic network transmission is added. Repository
tests use synthetic identity fixtures only, never real operator data.

## Audit-only recovery and current authority

Import validates exact bounded canonical input, rejects extra/duplicate/noncanonical
fields and unpaired surrogates, and stages unknown with zero network calls. The imported
controller exposes only an explicit audit query, not registration send/retry. It never
generates replacement IDs or audit event numbers. Existing registration POST/replay
behavior remains separate and unchanged.

The new fixed receipt proxy uses the existing exact default-off registration gate and
same-origin/private/no-store/size defenses. Each query revalidates a token-bound USER
session and successful strictly validated existing administrator-read authorization;
grant counts or caller assertions do not authorize it. Only then does it GET the exact
original audit using the same session credentials. No registration POST, activation,
mutable target read or speculative retry is performed. Current authorization failure
cannot turn an uncertain original outcome into a claim that nothing happened.

The original audit must match current actor, event number, REGISTER action, exact event
and entity types, entity UUID/reference and every expected payload field. Principal
audit stores an existing request digest rather than duplicating subject/name/issuer.
Recovery computes that existing SHA-256 format with the trusted server issuer and exact
canonical request: Python-compatible sorted compact JSON with raw Unicode, excluding
event number. Missing/mismatched digest stays unknown; imports cannot choose an issuer
or provide a digest as authority. Global/scoped grant payloads use their distinct
existing schemas, not an invented shared scope field.

The separate historical receipt confirms only original registration and its initial
DISABLED/SUSPENDED state. It never includes fabricated current_status, replayed or
revoked-session counts. It does not prove current roles/status, activate permissions or
replace current authorization. Real OIDC and live administrator acceptance remain external.

## Validation and finite completion boundary

Protocol, actual UI interactions and composed server-proxy synthetic tests cover all four
kinds, unknown exports, strict inputs, identity-data warnings, zero-network import,
explicit read-only queries, frozen IDs, session/admin revocation, foreign actors,
original-field/digest tampering, Python-produced Unicode digest vectors and historical
receipt privacy. Existing registration submission tests and all Batch/Changeover manual
recovery suites remain intact for the final finite integration review.

Exact local/review/PR/main CI/artifact/provider evidence is recorded in HANDOFF and the
final PR comment. No browser/public403 restriction is bypassed. Overall36/44=82% remains
unchanged until external milestone evidence exists. Closing all three implementation
packages and integration review does not mean real-provider/browser/company acceptance
or formal production release; no further automatic feature queue is selected.
