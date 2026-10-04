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
