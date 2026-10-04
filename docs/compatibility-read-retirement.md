# Compatibility read retirement follow-up

Initial inventory baseline: 4fc79aa4e04885465cc15a582cee101f235bc670.
Baseline API 0.18.20 completes 17/17 identified frontend read-consumer groups.
Current API 0.18.22 has 19 reviewed HTTP GET tombstones; see transitions below.
The denominator is unchanged. This does not remove or bound all legacy endpoints.
ROADMAP Phase 4 remains 8/9 because its endpoint acceptance wording is retained.

| Family retained at API 0.18.20 | Replacement / evidence | Initial review requirement |
| --- | --- | --- |
| `/api/v1/manufacturing/sites` and `/{site_code}` | manufacturing_views.py / manufacturing catalog/profile components | Bulk sites, lines and per-deployment history remain in production.py; review callers, then retire or explicitly bound old response |
| `/api/v1/organizations/{suppliers,customers,projects}` and rich profiles | organization_views.py / six migrated consumers | Top-level lists cap at 200 but child/release graphs remain; review rich child limits/retirement without silently changing count meaning |
| `/api/v1/changes/{request_no}` and `/{request_no}/coverage` | change_views.py / change_coverage_views.py | Legacy rich definitions/coverage/history retained; internal services and external callers need contract review |
| `/api/v1/issues/{issue_no}`, impact and assessment-history reads | issue_views.py | Legacy rich candidates/evidence/history retained; preserve exact judgment/execution semantics in any transition |
| Rich release downstream/evidence/components/policy/passport/readiness/compatibility reads | named groups 5–16 in read-consumer-migration.md | Review retained caller/service dependencies and individual response semantics before retirement/bounds |
| Legacy deployment detail/provenance and `/deployments` | bounded production profile/catalog | production.py bulk/history arrays remain; bounded profile still reuses detail helpers with history disabled |

This is a family-level follow-up inventory, not a declaration that every legacy
route is unbounded or that every backend/internal caller has been reviewed. Existing
bounded catalogs, exact scalar routes, commands, release-matrix and shared policy/
coverage service consumers remain in scope of their own contracts. At that API 0.18.20 baseline there was no
runtime route retirement or deprecation header; API 0.18.21/22 transitions below
record the subsequently implemented tombstones.

Next complete a route/caller inventory from the FastAPI route registry and repository
call sites. For each retained rich route, choose an explicit reviewed transition:
retire with a documented replacement, or bound parent/child transfer with complete
counts and clear pagination/truncation semantics. Preserve internal command/policy
services; do not silently truncate evidence and treat it as complete. Add contract
and representative growth regression tests. Only then mark the existing Phase 4
endpoint item complete. Approved identity/session and controlled submission follow;
public staging remains sample-only read-only.

## First reviewed runtime transition — API 0.18.21

Starting main: `827050736a6548bab3e77785b7c0b4701b8051d2`.
Eight concrete HTTP GET routes are now tombstones, not rich graph serializers:

| Retired route | Bounded successor |
| --- | --- |
| `/api/v1/organizations/suppliers` | `/api/v1/organization-views/suppliers` |
| `/api/v1/organizations/suppliers/{code}` | `/api/v1/organization-views/suppliers/{code}/summary` and `/items` |
| `/api/v1/organizations/customers` | `/api/v1/organization-views/customers` |
| `/api/v1/organizations/customers/{code}` | `/api/v1/organization-views/customers/{code}/summary` and `/items` |
| `/api/v1/organizations/projects` | `/api/v1/organization-views/projects` |
| `/api/v1/organizations/projects/{identifier}` | `/api/v1/organization-views/projects/{identifier}/summary` and `/items` |
| `/api/v1/manufacturing/sites` | `/api/v1/manufacturing-views/sites` |
| `/api/v1/manufacturing/sites/{site_code}` | `/api/v1/manufacturing-views/sites/{site_code}/summary` and `/lines` |

Repository caller review: the six organization consumers use organization-catalog/
profile components; manufacturing directory/profile use manufacturing-catalog/profile.
Their HTTP reads already use the successors. Other manufacturing URLs in frontend
are page links, not legacy API requests. Legacy helper calls in test_organizations,
test_manufacturing_catalog, test_organization_views and test_manufacturing_views are
internal comparison fixtures and remain callable. No known frontend HTTP caller
requires these eight responses. This review does not discover unknown external clients;
clients using these old routes must migrate, and the intentional HTTP break is documented.

Each tombstone returns 410 `legacy_read_retired`, the registered old route, safely
encoded successor URLs, required_collection_pin and instructions. Read the profile
summary first, then use its UUID `id` as organization_id or site_id for the bounded
child page. Catalogs use limit/offset and full filtered counts. Tombstones have no
DB dependency, no graph serialization, no data-presence lookup, no redirects or
silent truncation. Even a nonexistent parent or malformed query returns this same
retirement contract. Link rel=successor-version points to catalog/summary; no-store
prevents caching rollout responses. OpenAPI marks these GET routes deprecated with
410, not a successful old response. Known non-GET routes are not intercepted.

`organizations/release-matrix`, all bounded views, all 14 commands and reusable
production helpers are retained. Deployment detail/provenance and the remaining
families above still require review. This is the first runtime retirement slice,
not completion of the Phase 4 checkbox; ROADMAP remains 34/44. The baseline table
above describes API 0.18.20; these two families are now retired at the HTTP boundary.
See development-plan.md for the subsequent packages and dependencies.

## Second reviewed runtime transition — API 0.18.22

Starting main: `7048c797a5181d89ef72e7a9d0c978458ca54342`.
Eleven additional HTTP GET routes retire; cumulative explicit tombstones: 19.

| Retired route | Successor and exact scope |
| --- | --- |
| `/api/v1/deployments` | `/api/v1/production/catalog/deployments` |
| `/api/v1/deployments/{deployment_no}` | `/api/v1/deployments/{deployment_no}/profile`; changeover/batch catalogs with deployment_id=profile.id |
| `/api/v1/deployments/{deployment_no}/provenance` | Exact deployment profile; governance decisions using BOTH delivered release_id and snapshot_id from provenance.delivery |
| `/api/v1/batches` | `/api/v1/production/catalog/batches`; exact `/batches/{batch_no}` stays |
| `/api/v1/deliveries` | `/api/v1/distribution/catalog/deliveries` |
| `/api/v1/deliveries/{package_no}` | Delivery catalog with literal substring q; explicitly select exact package_no/revision/UUID, then exact revision profile |
| `/api/v1/deliveries/{package_no}/revisions/{revision}` | Exact `/profile`, bounded `/artifacts`; distributions scoped by delivery_package_id=profile.id |
| `/api/v1/distributions` | `/api/v1/distribution/catalog/distributions` |
| `/api/v1/distributions/{distribution_no}` | Exact `/profile`; authorizations scoped by distribution_id=profile.id |
| `/api/v1/authorizations` | `/api/v1/distribution/catalog/authorizations` |
| `/api/v1/authorizations/{authorization_no}` | Exact `/profile`; production deployment/batch catalogs scoped by authorization_id=profile.id |

Caller review: production-catalog renders deployments/changeovers/batches, and the
Batch page uses the exact bounded batch read. Deployment page appends `/profile`,
not old detail/provenance. Distribution catalog uses three bounded catalogs;
delivery detail uses exact revision profile/artifacts; distribution/authorization
pages append `/profile`. Command-draft URLs sharing old catalog paths are POST
commands and stay registered. No active repository frontend GET requires these
11 responses. Direct legacy calls in test_actual_retry, test_deployment_provenance,
test_deployment_profile, test_distribution_catalog, test_delivery_revision,
test_delivery_profiles, test_distribution_detail, test_authorization_detail and
test_distribution_profiles are comparison/compatibility fixtures; their functions
stay callable. Shared serializers remain available to scalar profiles with history
loading explicitly disabled. Unknown external HTTP clients must migrate.

Route/caller registry inspection confirms one tombstone per retired path; concrete
matching does not intercept profile/artifacts child reads, catalogs or POST paths.
Retirement never opens a DB session or invokes any organization/production/
distribution graph helper. Return 410 before old identity/query/revision validation;
nonexistent parents and invalid old revision values do not reveal existence.
Named path parameters are encoded separately, including revision. Header first
successor is a concrete URL; descriptive instructions retain parameter templates
where an exact UUID must first be obtained from an active profile/catalog.

Do not select a latest delivery revision implicitly, treat q as exact identity,
substitute actual deployment software for delivered decision scope, or infer a
missing provenance.delivery decision scope. Counts remain observations, not grants
or remaining batch capacity. Consumers use limit/offset and full counts in each
successor's existing contract. No evidence is silently truncated by retirement.

The initial family table is an API 0.18.20 baseline: organization/manufacturing and
legacy deployment HTTP reads are now retired. Remaining review includes SCR/Issue,
release evidence/policy/component/passport/readiness families plus governance and
audit compatibility routes; not every retained route is unbounded. Internal policy/
command consumers must be preserved. Phase 4 remains 8/9 and ROADMAP 34/44 until
that reviewed scope is fully retired/bounded. No schema/provider/grant/write change.

## Third reviewed runtime transition — API 0.18.23

Starting main: `51978c5b0ff70bda78aedc98ea95ff7636d3a3e0`.
Eight SCR/Issue GET routes retire; cumulative explicit tombstones: 27.

| Retired route | Bounded successor |
| --- | --- |
| `/api/v1/changes` | `/api/v1/change-catalog/requests` |
| `/api/v1/changes/{request_no}` | `/api/v1/change-views/{request_no}/summary` and independent criteria/issues/points/plans |
| `/api/v1/changes/{request_no}/coverage` | `/api/v1/change-coverage-views/{request_no}/summary` and independent candidates/gaps/groups/items/assignments |
| `/api/v1/issues` | `/api/v1/change-catalog/issues` |
| `/api/v1/issues/{issue_no}` | `/api/v1/issue-views/{issue_no}/summary` and changes/candidates/assessments |
| `/api/v1/issues/{issue_no}/impact` | Issue summary plus bounded candidates and complete assessment history |
| `/api/v1/issues/{issue_no}/impact/{release_id}` | Exact impact summary and bounded components/verification |
| `/api/v1/issues/{issue_no}/impact-assessments` | Issue summary and paged assessments with complete counts |

Repository review: change-catalog consumers use bounded directories; SCR detail,
coverage, Issue detail and exact impact pages use change-views/change-coverage-views/
issue-views and their independent collections. Command-draft URLs containing
changes/issues are POST commands, not old GET consumers. Direct calls in change
_detail/change_coverage/issue_impact/impact_assessments/issue_views tests are retained
comparison fixtures. No active repository frontend HTTP caller needs these eight
responses. Shared report_coverage, candidate/evidence/judgment helpers, assignment
and assessment writes remain; no internal command/policy service is deleted.
Unknown external HTTP clients must migrate this deliberate response-contract break.

Read scalar summary first and use exact change_id/issue_id for children. SCR
coverage carries selected release plus historical snapshot_no or snapshot_id,
then uses summary change_id/release_id/snapshot_id pins and none sentinels.
Issue impact evidence carries exact release UUID and optional selected Snapshot;
children carry summary issue_id/snapshot_id, preserving the recorded judgment
Snapshot and exact frozen execution scope. Candidate membership is review scope,
not impact or permission. The old bounded-but-truncated assessment head is retired
in favor of navigable complete history; not every route in this slice was unbounded.

Tombstones return 410 before old number/UUID/query validation and do no database/
graph work. They do not forward query selections or redirect; instructions require
clients to carry historical selection explicitly to the successor. No latest
substitution or silent evidence truncation is performed. All 14 write routes,
bounded catalogs/summary/children and internal helpers remain. No migration,
identity/provider/grant change or public-write enablement.

For ongoing plan reporting, development-plan-progress.json fixes nine compatibility
families and one full-inventory closure milestone. Its 53 candidate paths include
all 27 tombstones and retained paths needing review; candidates can already be
scalar/bounded or still actively consumed and must not be blindly retired.
Five families (organization/manufacturing/production/distribution/SCR-Issue) resolve,
so plan 1 advances from 4/10=40% to 5/10=50%. Release/ASR, Snapshot, DVP,
governance/audit and the closure gate remain. This independent milestone percentage
does not close Phase 4 or change ROADMAP 34/44. Reporting checks enforce completed
family route evidence and all tombstones appearing in the inventory.

## Fourth slice — exact Snapshot, API 0.18.24

| Retired GET | Successors |
| --- | --- |
| `/api/v1/snapshots/{snapshot_no}` | Exact `/summary`, independent `/artifacts` and `/rules` |
| `/api/v1/snapshots/{snapshot_no}/compare/{target_no}` | `/comparison/{target_no}/summary` and `/files` |

Frontend snapshot detail/manifest and comparison consumers already use these
successors. Direct snapshot_detail/compare_snapshots calls in regression tests remain
legacy comparison fixtures; their functions and _manifest are retained. No repository
HTTP consumer needs the two retired responses. External callers must migrate.
Read exact summary, then pass its id as snapshot_id to artifact/rule pages.
Comparison files require source.id as source_id and target.id as target_id from
comparison summary, preserving both historical identities. Same-release validation,
duplicate frozen identity rejection, show filtering, full SQL counts and independent
pages remain. Tombstones are DB-free, do not validate old queries and encode both
path parameters separately. All 14 commands remain; no migration or public write change.

The fixed 53-path candidate inventory now contains 29 retired routes. Six of ten
plan-1 milestones pass: 50% → 60%. Release/ASR, DVP, governance/audit and full closure
remain. DVP catalog/history are bounded, but dvp_profile still loads linked acceptance
criteria, change points and issues without pagination. Therefore the DVP family is
not completed or retired in this slice. Next add bounded owned relation reads and
migrate the frontend before closing that milestone. ROADMAP stays 34/44 (77%).

## Fifth slice — DVP, API 0.18.25

Retired GET /api/v1/testing/dvp and /id/{item_id} now return DB-free HTTP410.
Successors: /catalog, exact /id/{item_id}/profile, /relations/{criteria,points,issues}
and /executions. Legacy list_dvp/dvp_item_detail functions remain internal fixtures.
Frontend directory already uses /catalog; exact detail now consumes profile counts
and independent relation pages. No active repository HTTP caller needs old responses.

Profile contract intentionally replaces linked_acceptance/linked_change_points/
linked_issues arrays with relation_counts. Each relation page requires dvp_item_id
matching the path's UUID; missing/malformed pin422, wrong owner404. Strict queries
reject unknown fields; limit1..100/default50 and offset0..100000/default0. Envelope:
item_id/kind/total/limit/offset/next_offset/items; rows contain id/number/text. Counts
use SQL EXISTS and complete SQL aggregates. Order is display number then stored UUID,
including nonunique criterion/change-point numbers. No automatic truncation or bulk
fallback. Empty end windows retain total and first-page navigation.

Execution history adds item_id to its envelope, preserving limit/before_number,
full total and release_id/optional historical snapshot_no. Context resolution is
now explicitly LIMIT1. Profile release selector remains bounded100 with a truncation
marker; it is not full history. Relation pages preserve all other cursors and history
filters; history links/filter form preserve relation selection. Invalid one page
leaves other relations available; foreign/stale parent fails closed. Default Chinese
and selectable English remain. Public sample remains read-only; all14 POSTs retained.

New SQLite/PostgreSQL growth tests cover105 linked records per relation, tied display
numbers, stable SQL read count/bounded rows, complete navigation and sibling isolation.
Frontend tests cover independent cursors, exact pins, mismatch/failure/empty windows.
53 candidates remain fixed, retired GETs29→31. DVP milestone now complete:
plan1 6/10=60%→7/10=70%; release/ASR, governance/audit and full closure remain.
No schema/provider/grant change; ROADMAP remains34/44=77%, read consumers17/17.

## Sixth slice — governance/audit, API0.18.26

| Retired GET | Successors |
| --- | --- |
| `/api/v1/approvals` | `/api/v1/governance/approvals` |
| `/api/v1/approvals/{approval_no}` | Exact governance `/summary`, independent `/steps` and `/actions` |
| `/api/v1/activity` | `/api/v1/audit/events`; exact `/activity/{event_no}` remains |

Frontend approval directory/actions already use governance catalogs; audit directory
uses audit/events and exact event pages use retained activity/{event_no}. Approval
detail now reads scalar summary and independently paged steps/actions instead of the
200-row step preview. Old dashboard list_approvals/get_approval and activity list_activity
are retained direct test fixtures; shared audit payload/release-link helpers and all14
writes remain. No active repository HTTP caller needs the three retired responses.
Unknown external clients must migrate the deliberate HTTP410 response break.

Summary resolves original recorded target/Snapshot, not latest. Full step_total and
action_total use SQL counts; steps require exact approval_id with strict pagination.
Action-history pin is optional for compatibility; frontend always sends it and checks
returned approval_id/approval_no. Step pages check both parents plus requested window.
Independent cursors/filter forms preserve other child selection. >200 steps are now
fully navigable; visible pending/waiting step links prepare that exact UUID only,
without current-step inference, approval transitions or authenticated submission.
The retained bounded governance profile still explicitly labels its200-row preview.

Old activity was already bounded but exposed a truncated head/payload directory; its
retirement replaces it with complete catalog navigation and separate exact payload.
UUID actor identity, declared actor names, time bounds and original event context
remain distinct. Tombstones perform no DB lookup or old query validation. Exact audit
payload links, all bounded successors and commands remain. No schema/provider/grant
or public-write change. Default Chinese and selectable English remain.

Fixed53 candidates remain; retired GETs31→34. Governance/audit milestone resolves:
plan1 7/10=70%→8/10=80%. Release/ASR and full closure remain; ROADMAP34/44=77%
and17/17 read consumers are unchanged. Growth tests verify205 steps, fixed read-query
count, bounded rows, complete traversal, exact owner validation and PostgreSQL parity.
