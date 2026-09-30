# SoftwareLifeCycle

Automotive software lifecycle governance platform for BMS / ECU software.

The implemented traceability chain is:

`SCR → DVP → Snapshot → Readiness → Approval → Release Decision → Delivery → Distribution → Production Authorization → Deployment → Changeover → Batch`

The demo dataset follows one consistent frozen release path:

`SNAP-008 → APR-0121 → RD-0081 → DP-0226 → DIST-0326 → PA-0081 → DEP-0081 → CO-0032 → PB-1005-A`

The Activity workspace is backed by an append-only audit ledger. PostgreSQL rejects updates and deletes to formal audit events; corrections must be recorded as new events.

## Stack

- Next.js + TypeScript, deployed to Cloudflare Workers through OpenNext
- FastAPI + SQLAlchemy + Alembic
- PostgreSQL
- Docker Compose for a complete local environment

## Local environment

```bash
cp .env.example .env
docker compose up --build
```

Open the web application at `http://localhost:3000` and the API documentation at `http://localhost:8000/docs`.

The API container performs these steps in order:

1. applies every Alembic migration;
2. loads the idempotent demo dataset when `SEED_ON_STARTUP=true`;
3. starts FastAPI;
4. becomes healthy only when PostgreSQL is reachable and is on the required migration revision.

Set `SEED_ON_STARTUP=false` for a production database after the demo data is no longer wanted.

## Health checks

- `GET /health` — compatibility health endpoint
- `GET /health/live` — process liveness
- `GET /health/ready` — database connectivity and schema revision readiness

Use `/health/ready` for load balancers and container health checks.

## Cloudflare frontend

The root Wrangler configuration deploys the Worker to `softwarelifecycle.whf969.com`.

```bash
npm ci
npm run build
npm run deploy
```

Configure `API_BASE_URL` as a Cloudflare Worker runtime environment variable pointing to the public FastAPI origin, for example `https://api.example.com`. It is intentionally a server-side variable: the frontend pages query FastAPI from the Worker and do not expose an internal container address to browsers.

The dashboard reads `GET /api/v1/dashboard/summary` for current counts, release verification coverage and the five latest audit events. Global search uses `GET /api/v1/search?q=...&limit=50` to look up lifecycle identifiers, names, artifact filenames and SHA fragments. Search requires a nonblank query (maximum 100 characters), returns at most 100 results, and does not require a database migration. If the API is unavailable, these pages show an unavailable state instead of static demo metrics or fabricated search matches.

Both SSR and ASR profiles link to `/releases/{release_id}/snapshots`. The read-only API `GET /api/v1/releases/{release_id}/snapshots` lists that release's freeze records by snapshot number descending, with full content hashes and the current snapshot marker. `limit` defaults to 20 (1–100); use the returned `next_before_number` as `before_number` to fetch older records. `total` always counts all snapshots for that release, regardless of the cursor. Unknown releases return 404; releases without snapshots return an empty list. Each record opens `GET /api/v1/snapshots/{snapshot_no}` and its exact frozen manifest. The current marker identifies the newest freeze, not approval or production permission. Neither endpoint changes history, Seed, or the schema.

Snapshot detail and history link to `/snapshots/{snapshot_no}/compare`. Choose a target snapshot from the same release; the page defaults to the newest freeze and can show changed files or all files. `GET /api/v1/snapshots/{snapshot_no}/compare/{target_no}` returns added, removed, modified and unchanged counts, frozen before/after fields, and frozen version/type metadata changes. Files match by component code and filename; renames are removal plus addition. Comparison checks file type, component version, SHA-256, classification, distribution level, AI policy and frozen recipient rules independently of content-hash equality. Rule ordering and row IDs do not create differences. Missing snapshots return 404; different releases or duplicate file identities return 409. This is a read-only manifest comparison, not a binary diff, approval decision, or source-file policy lookup; storage references are not exposed.

The `/releases/matrix` page uses `GET /api/v1/organizations/release-matrix` to browse every recorded ASR with its customer, project, SSR baseline and latest frozen snapshot. Filters include `region` (APAC, EUROPE, AMERICAS, OTHER, UNASSIGNED), exact customer code, project UUID, ASR status and `q` (customer/project/software names, codes or version). Search treats `%` and `_` literally. Pagination uses `limit` (1–100, default 50) and `offset` (0–100000); the returned total and summary describe all filtered records. Without an ASR-specific filter, empty customers and projects are preserved. Migration `0011_customer_regions` adds an optional constrained customer region; existing records stay unassigned and Seed does not guess geography. The matrix is release history, not evidence of a production deployment. Customer and project profiles link to their filtered histories.

The Activity page uses the existing `GET /api/v1/activity` filters for event type, entity type, entity reference and a limit of 50, 100 or 200. An event opens `/activity/{event_no}`, backed by `GET /api/v1/activity/{event_no}`; dashboard and search event links open the same detail. An empty ledger or unavailable API never displays demo events as formal history.

The DVP catalog at `/testing/dvp` displays recorded items from `GET /api/v1/testing/dvp` without a demo fallback. An item opens `/testing/dvp/{item_id}`, backed by `GET /api/v1/testing/dvp/id/{item_id}`. The detail lists every recorded execution with its own release, snapshot, test release and result. A prior snapshot's PASS is history, not evidence for a newer snapshot. The list's latest result is across recorded executions for each item; release-specific readiness remains scoped to the relevant snapshot.

SCR pages read `GET /api/v1/changes` and `GET /api/v1/changes/{request_no}`. The detail displays stored requirement text, acceptance criteria, linked issues, change points, and DVP plan/item links without assigning a test result or release to an SCR by inference. Issue catalog and SCR pages show empty or unavailable states instead of demo fallback rows; an unavailable API does not fabricate formal records.

Approval catalog and detail pages read `GET /api/v1/approvals` and `GET /api/v1/approvals/{approval_no}`. Detail resolves the exact target release and snapshot, recorded approval steps, and decision actions; actions display their linked step roles when present. Empty or unavailable API responses do not substitute demo approvals. The displayed snapshot hash is a stored reference, not an independent file recheck.

Suppliers, customers and projects use read-only `/api/v1/organizations/{suppliers|customers|projects}` list and detail endpoints. Project detail links use the UUID because project codes are only unique within a customer. Legacy project-code links work when the code identifies exactly one project; ambiguous codes return HTTP 409. Organization pages display an unavailable state when FastAPI cannot be reached.

The Application Releases list reads `GET /api/v1/releases/application`, including customer, project, standard base version and latest snapshot. Every application release links to a read-only profile at `/releases/application/{release_id}`, backed by `GET /api/v1/releases/application/id/{release_id}`. The profile shows snapshot-bound coverage only when a snapshot exists. The existing ASR 2.3.4 workspace remains available as a detailed demo view.

The profile also reads `GET /api/v1/releases/application/id/{release_id}/evidence` for the frozen SnapshotArtifact manifest and the latest DVP execution for each item on the current snapshot. Historical executions from other snapshots are counted separately; storage references are not returned. This is read-only and does not modify formal history.

`/releases/application/{release_id}/readiness` reads `GET /api/v1/releases/application/id/{release_id}/readiness`. It evaluates the exact ASR UUID, preserving raw and effective gate results and showing only approved exceptions for its current snapshot. The older version-based readiness endpoint remains for compatibility, but a version alone may be ambiguous across software products.

`/releases/application/{release_id}/artifacts` reads `GET /api/v1/releases/application/id/{release_id}/snapshot-policy`. It displays the latest frozen SnapshotArtifact manifest and its frozen recipient rules for the exact ASR UUID. The response never returns file storage references; these recorded rules do not by themselves authorize a delivery. The older version-based `/artifacts` route displays current release configuration and remains for compatibility.

`/releases/application/{release_id}/components` reads `GET /api/v1/releases/application/id/{release_id}/components`. It shows the ASR's recorded component delta declarations and exact links to its base SSR components. Missing links or missing SSR component records remain explicit unknowns; no inherited effective version is inferred from a matching component name or a demo table.

`GET /api/v1/releases/application/id/{release_id}/downstream` lists deliveries, distributions, authorizations, deployments, changeovers and batches linked through their stored foreign keys. The application release profile displays these records with parent references and snapshot identifiers. It flags an actual deployment or batch recorded for a different release instead of treating a planned authorization as proof of production use. This read-only endpoint returns 404 for a missing or non-application release.

Deployment detail reads `GET /api/v1/deployments/{deployment_no}/provenance` to resolve its authorization, distribution and delivery through stored links, then lists all release decisions for that delivery's release and snapshot with their approval numbers. Missing links are displayed as missing; the page no longer inserts fixed Demo identifiers into the provenance section.

The Distribution navigation now opens a read-only delivery catalog at `/distribution/deliveries`. Each package revision has its own detail URL `/distribution/deliveries/{package_no}/{revision}` backed by `GET /api/v1/deliveries/{package_no}/revisions/{revision}`. Search and release downstream links retain the exact revision. The older `/distribution/deliveries/new` demo URL redirects to the catalog. An unavailable API does not substitute the seeded package for an unrelated revision.

`/distribution/distributions` lists all distribution records from `GET /api/v1/distributions`; `/distribution/distributions/{distribution_no}` shows the recipient, exact delivery revision, sent and acknowledged times, and authorizations linked by `distribution_id`. Search, Activity, release downstream, and delivery details link to these records. These pages are read-only and do not infer production authorization from acknowledgment.

`/distribution/authorizations` and `/distribution/authorizations/{authorization_no}` browse the recorded production authorization scope and its linked distribution, exact delivery revision, deployments, and batch usage. The detail API `GET /api/v1/authorizations/{authorization_no}` reports actual release and snapshot matches separately when a deployment has reported actual software. A count of unfilled batch slots is informational, not permission to start production. The older `/distribution/authorizations/new` demo route redirects to the catalog; unavailable API data never substitutes PA-0081 for another authorization.

`/production/batches` and `/production/batches/{batch_no}` use read-only `GET /api/v1/batches` and `GET /api/v1/batches/{batch_no}`. A batch detail shows its recorded software, deployment, authorization and optional changeover, comparing the stored release and snapshot identifiers separately. Search, Activity, release trace, authorization and deployment pages link directly to the batch. Identifier comparisons are not independent evidence of physical production-line flashing.

Issue detail pages read `GET /api/v1/issues/{issue_no}/impact` to trace linked SCRs to their software product and show candidate SSR/ASR versions for manual impact review. Actual deployments and production batches attached to each candidate release are counted separately. Sharing a software product does not establish that a version is affected; the endpoint deliberately labels the result as candidates. Unlinked issues produce no inferred releases.

For Cloudflare Workers Builds, also add any variables needed during static generation under **Build variables and secrets**. The deploy command uses `--keep-vars`, so dashboard-managed runtime variables are preserved.

## Backend deployment

For a sample-only online test database, API service, read-only guard, Cloudflare connection, and smoke check, see [Test database and API deployment](docs/staging-api.md). The test environment should contain demo records only; user authentication and project permissions are not implemented yet.

Build and run `backend/Dockerfile` with a managed PostgreSQL database. At minimum configure:

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE
CORS_ORIGINS=https://softwarelifecycle.whf969.com
SEED_ON_STARTUP=false
```

For the first demo deployment, `SEED_ON_STARTUP=true` safely creates or updates the named demo records. The seed is idempotent, but production data should normally be provisioned separately.

Before sending traffic, verify:

```bash
curl --fail https://API_HOST/health/ready
curl --fail https://API_HOST/api/v1/distributions/DIST-0326
curl --fail https://API_HOST/api/v1/authorizations/PA-0081
curl --fail https://API_HOST/api/v1/deployments/DEP-0081
```

## Verification

```bash
cd backend && pytest -q
cd frontend && npm run build
```

The product baseline is available at `docs/baseline-v1.1.html`.


### Issue impact evidence and judgments

`GET /api/v1/issues/{issue_no}/impact/{release_id}` shows the latest **frozen** snapshot, its frozen component versions, and the latest execution per linked DVP item matching that exact release and snapshot. Candidate software matching and a PASS result do not establish issue impact. The Issue page links to these evidence pages and reads append-only judgment history from `GET /api/v1/issues/{issue_no}/impact-assessments` (default latest 50, maximum 200, `truncated` indicates more history).

`POST /api/v1/issues/{issue_no}/impact-assessments` accepts `request_id` (client-generated UUID), `release_id`, `snapshot_id`, `decision` (`AFFECTED`, `NOT_AFFECTED`, `NEEDS_REVIEW`), nonblank `reason` and `actor_name`, and optional `evidence_ref`. The snapshot must be frozen, belong to the release, and the release software must match a linked SCR. New requests return 201; identical retries return 200 without another audit event; reusing an ID with different content returns 409. Correct a judgment by submitting a **new** request ID; earlier records remain. Judgment and `ISSUE_IMPACT` audit event commit in the same transaction. Reviewer names are declared inputs, not authenticated identities. This write endpoint remains blocked by `READ_ONLY_MODE=true` on the public test API; no public write form is exposed.

Migration `0012_issue_impact_assessments` creates the history table with PostgreSQL UPDATE/DELETE rejection trigger. No existing migration or Seed data is changed, and a judgment for an older snapshot is not automatically applied to the latest snapshot. History has a bounded latest-record list, without a pagination cursor yet. PostgreSQL locking serializes writes for one issue; SQLite tests verify transaction behavior but do not simulate concurrent PostgreSQL connections.

### SCR completeness and acceptance coverage

`GET /api/v1/changes/{request_no}/coverage` reports missing requirement text, acceptance criteria, change points, DVP plans/items, and explicit test assignments for criteria, change points and linked Issues. Missing definitions do not become 100% coverage. Tests from another SCR plan are flagged and excluded. Candidate releases match software and, for ASRs, the recorded customer/project scope; they do not prove incorporation of a change. The first 100 candidates are returned with a truncation flag; direct selection remains available beyond that list.

Optional `release_id` (UUID) selects verification context; `snapshot_no` selects a historical frozen snapshot of that release, otherwise the latest frozen snapshot is used. Selecting a snapshot without a release returns 422; mismatched scope/snapshot returns 409; missing SCR/release returns 404. Only executions for the exact release and snapshot count, and the greatest execution number per item wins. A later FAIL overrides an earlier PASS. Assignment percentage and all-assigned-tests PASS counts are separate; with no frozen context execution counts are unknown. The full SCR plan includes tests with no assignment, rather than silently omitting pending tests. This report does not change release readiness/approval gates. Definitions and assignments are current records and are **not** frozen by historical release snapshots.

`POST /api/v1/changes/{request_no}/acceptance-dvp-links` accepts `request_id` (UUID), `criterion_id`, `dvp_item_id`, nonblank `actor_name` and `reason`. Both criterion and DVP plan must belong to that SCR. New assignments return 201; identical request retries return 200 with no duplicate audit; conflicting IDs or repeated criterion/test pairs return 409. Assignment and `ACCEPTANCE_DVP` audit event commit atomically. A criterion may require multiple tests: all assigned tests must PASS in the selected context to display PASSED. The coverage response includes assignment IDs, declared reviewer, reason and time. Reviewer names are not authenticated identities.

Migration `0013_acceptance_dvp_links` adds the assignment table, unique criterion/test pair and PostgreSQL append-only trigger. Existing records and Seed are unchanged; acceptance links are not inferred from test names or created by Seed. No assignment removal/revocation workflow is provided yet. Public test API remains `READ_ONLY_MODE=true`, and `/changes/{request_no}/coverage` exposes only read/query controls. Writes are for a controlled local development environment until authentication and permissions are implemented.
