# Compatibility read retirement follow-up

Reviewed main baseline: 4fc79aa4e04885465cc15a582cee101f235bc670.
Current package API 0.18.20 completes 17/17 identified frontend read-consumer groups.
The denominator is unchanged. This does not remove or bound all legacy endpoints.
ROADMAP Phase 4 remains 8/9 because its endpoint acceptance wording is retained.

| Retained family | Current replacement / evidence | Remaining review |
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
coverage service consumers remain in scope of their own contracts. There is no
runtime route retirement or deprecation header in this package.

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
