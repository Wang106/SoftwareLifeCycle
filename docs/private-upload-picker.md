# Default-off single-file private upload

The only new-file entry is a verified application-component declaration receipt.
Its `component_id` is the upload object, never the definition UUID or SSR baseline
UUID. The page reuses the complete PRIVATE_UPLOAD_MODE/API/origin and browser
session configuration gate; no runtime setting is supplied or enabled here.
Existing backend authorization and same-origin proxy checks remain authoritative.

Selection first obtains and verifies the trusted upload context. Before reading
or hashing any bytes, it rejects sizes above the smaller of admission_max_bytes
and 8 MiB. The preview binds exact component, bytes, SHA-256 and reason. File or
reason changes, target replacement and cancellation invalidate confirmation and
old callbacks. Only explicit current confirmation starts reserve and one PUT.
No file name or content is persisted or sent as JSON. Content uses the dedicated
binary proxy; the old 32 KiB JSON routes remain unchanged.

A same-origin Web Lock guards a localStorage journal claim before reserve. The
journal contains only version and random request UUID. Missing locks, unavailable
or corrupt storage fail closed. A claim is never cleared by this slice, including
after success: this is one upload attempt per retained browser journal, not a
multi-upload workflow. There is no user-facing reset or retry action. This
conservative limitation avoids resetting an uncertain operation. Cross-browser,
cleared/modified storage, direct API clients and compromised same-origin scripts
are outside this local duplicate guard; server permissions still apply.

Cancellation after claim, response loss and refresh retain receipt-only recovery.
A new controller reads the original request ID without automatically querying or
resending. RESERVED, missing/forbidden/invalid replies and intermediate states do
not establish failure or unlock creation. Receipt lookup calls only the existing
same-origin receipt route. Recovery is available even without a current component
receipt; it displays the actual original receipt component and explicitly warns
if it differs from the current declaration. It does not relabel recovered bytes.
File bytes and SHA preview live only in memory. Unmount/cancel clears references;
JavaScript garbage collection is not a guarantee of physical memory erasure.

Network completion never means stored success. Only a strictly parsed original
STORED_PRIVATE receipt is shown as private storage confirmation; existing proxy
independently queries the backend receipt after PUT. It is not a scan verdict,
download permission, Artifact creation, distribution approval or release readiness.

Validation uses synthetic identities, bytes and fetch/storage/React hook doubles.
The 65,539-byte binary fixture includes non-UTF-8 bytes and checks exact body/hash.
This package does not claim a real browser-to-proxy-to-temporary-filesystem chain.
That additive browser wiring and actual temporary storage evidence remain a
separate slice; existing strict browser gates remain intact. No real files,
storage root/capacity, identity configuration, deployment, image or VM operations.
