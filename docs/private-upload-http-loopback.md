# Synthetic real-HTTP private-upload evidence

The Linux-only tests in `backend/tests/test_private_upload_http_loopback_postgres.py`
join existing production FastAPI routes/authentication, Uvicorn on a prebound
127.0.0.1 ephemeral socket, a disposable PostgreSQL schema using the established migration pattern, and actual
LocalArtifactStorage files. No production code, dependencies or runtime settings
are changed. Test settings/keys exist only inside the fixture and are restored.

The PostgreSQL URL must be the existing disposable loopback service. The fixture
uses the established unique schema migration/teardown pattern, reuses component_pg
and upload_pg, and additionally verifies
zero checked-out connections and absence of its schema after teardown. No company,
old database or remote service is an allowed target. Without TEST_POSTGRES_URL,
the existing TEST_POSTGRES_URL skip convention applies locally; ordinary CI rejects skipped backend evidence.

Normal and lost-response cases send 65,539 synthetic binary bytes. JWT signatures,
principal/project/software authorization and the token-bound BrowserSession remain
real validation code; only test public-key lookup and DB/runtime dependencies are
wired to synthetic resources. This is not a real OIDC provider or TLS test.

The loss hook waits for the complete application response, verifies STORED_PRIVATE
on a separate DB session, original request/component/actor/length/digest, five
revision audit events and unchanged Artifact count. It independently opens and
hashes the closed Linux file, including the existing retained .part/.blob hard-link
pair. Only then does it deliberately leave the HTTP response body incomplete.
The client must get RemoteProtocolError. A fresh client only GETs the original
receipt: reservation request, PUT and actual storage commit each remain exactly one;
DB audit, disk identity, length and SHA-256 remain unchanged. This does not test a
browser refresh or claim a global exactly-once guarantee.

Unsigned, disabled and revoked-project cases refuse without a reservation or
storage. Cleanup joins only the owned server thread, verifies no Uvicorn tasks or
connections and no held transfer permit, then validates directory identity and
all recorded filenames/inodes before unlinking only those files and the owned root.
Unknown or changed files fail cleanup explicitly, rather than broad deletion.

Run with the existing backend pytest/CI commands. Local helper/SQLite diagnostics
are separate from PostgreSQL CI results; exact candidate evidence lives in its PR.
Existing macOS signed Chrome 4+16+16 tests remain unchanged. A future browser-to-real
Linux service test needs separately reviewed Linux browser provenance/sandbox and
runtime wiring. Company storage, real identity, TLS, scanning/distribution and
multi-version continuous uploads remain unaccepted.
