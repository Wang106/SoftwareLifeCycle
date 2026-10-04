"""Explicit HTTP tombstones for reviewed legacy reads, with no DB dependency.

Only registered GET routes retire. Internal comparison helpers and all commands
remain available; replacement collection reads require the summary's UUID pin.
"""
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["retired-compatibility-reads"])

# Concrete paths avoid intercepting release-matrix or any bounded child route.
RETIRED_READS = tuple(
    (f"/api/v1/organizations/{kind}",
     (f"/api/v1/organization-views/{kind}",), None)
    for kind in ("suppliers", "customers", "projects")
) + tuple(
    (f"/api/v1/organizations/{kind}/{{{parameter}}}",
     (f"/api/v1/organization-views/{kind}/{{identifier}}/summary",
      f"/api/v1/organization-views/{kind}/{{identifier}}/items"), "organization_id")
    for kind, parameter in (("suppliers", "code"), ("customers", "code"), ("projects", "identifier"))
) + (
    ("/api/v1/manufacturing/sites", ("/api/v1/manufacturing-views/sites",), None),
    ("/api/v1/manufacturing/sites/{site_code}",
     ("/api/v1/manufacturing-views/sites/{identifier}/summary",
      "/api/v1/manufacturing-views/sites/{identifier}/lines"), "site_id"),
)


# Second reviewed slice: production/distribution arrays and rich histories.
RETIRED_READS += (
    ("/api/v1/deployments", ("/api/v1/production/catalog/deployments",), None),
    ("/api/v1/deployments/{deployment_no}",
     ("/api/v1/deployments/{deployment_no}/profile",
      "/api/v1/production/catalog/changeovers", "/api/v1/production/catalog/batches"), None),
    ("/api/v1/deployments/{deployment_no}/provenance",
     ("/api/v1/deployments/{deployment_no}/profile", "/api/v1/governance/decisions"), None),
    ("/api/v1/batches", ("/api/v1/production/catalog/batches",), None),
    ("/api/v1/deliveries", ("/api/v1/distribution/catalog/deliveries",), None),
    ("/api/v1/deliveries/{package_no}",
     ("/api/v1/distribution/catalog/deliveries?q={package_no}",), None),
    ("/api/v1/deliveries/{package_no}/revisions/{revision}",
     ("/api/v1/deliveries/{package_no}/revisions/{revision}/profile",
      "/api/v1/deliveries/{package_no}/revisions/{revision}/artifacts",
      "/api/v1/distribution/catalog/distributions"), None),
    ("/api/v1/distributions", ("/api/v1/distribution/catalog/distributions",), None),
    ("/api/v1/distributions/{distribution_no}",
     ("/api/v1/distributions/{distribution_no}/profile",
      "/api/v1/distribution/catalog/authorizations"), None),
    ("/api/v1/authorizations", ("/api/v1/distribution/catalog/authorizations",), None),
    ("/api/v1/authorizations/{authorization_no}",
     ("/api/v1/authorizations/{authorization_no}/profile",
      "/api/v1/production/catalog/deployments", "/api/v1/production/catalog/batches"), None),
)


# Third reviewed slice: SCR/Issue graphs, coverage and impact evidence/history.
RETIRED_READS += (
    ("/api/v1/changes", ("/api/v1/change-catalog/requests",), None),
    ("/api/v1/changes/{request_no}",
     ("/api/v1/change-views/{request_no}/summary", "/api/v1/change-views/{request_no}/criteria",
      "/api/v1/change-views/{request_no}/issues", "/api/v1/change-views/{request_no}/points",
      "/api/v1/change-views/{request_no}/plans"), "change_id"),
    ("/api/v1/changes/{request_no}/coverage",
     ("/api/v1/change-coverage-views/{request_no}/summary",
      "/api/v1/change-coverage-views/{request_no}/candidates",
      "/api/v1/change-coverage-views/{request_no}/gaps",
      "/api/v1/change-coverage-views/{request_no}/items"), "change_id"),
    ("/api/v1/issues", ("/api/v1/change-catalog/issues",), None),
    ("/api/v1/issues/{issue_no}",
     ("/api/v1/issue-views/{issue_no}/summary", "/api/v1/issue-views/{issue_no}/changes",
      "/api/v1/issue-views/{issue_no}/candidates", "/api/v1/issue-views/{issue_no}/assessments"), "issue_id"),
    ("/api/v1/issues/{issue_no}/impact",
     ("/api/v1/issue-views/{issue_no}/summary", "/api/v1/issue-views/{issue_no}/candidates",
      "/api/v1/issue-views/{issue_no}/assessments"), "issue_id"),
    ("/api/v1/issues/{issue_no}/impact/{release_id}",
     ("/api/v1/issue-views/{issue_no}/impact/{release_id}/summary",
      "/api/v1/issue-views/{issue_no}/impact/{release_id}/components",
      "/api/v1/issue-views/{issue_no}/impact/{release_id}/verification"), "issue_id"),
    ("/api/v1/issues/{issue_no}/impact-assessments",
     ("/api/v1/issue-views/{issue_no}/summary", "/api/v1/issue-views/{issue_no}/assessments"), "issue_id"),
)

MIGRATION_INSTRUCTIONS = {
    "/api/v1/changes/{request_no}": (
        "Read the exact SCR summary, then pass its id as change_id to each bounded "
        "criteria/issues/points/plans page. Use independent limit/offset and full counts."),
    "/api/v1/changes/{request_no}/coverage": (
        "Read the coverage summary with the explicit release_id and optional historical "
        "snapshot_no or snapshot_id selection. Use its change_id, release_id and "
        "snapshot_id pins for bounded children; preserve none sentinels. Do not "
        "replace a selected historical snapshot with the latest. Retirement does "
        "not forward or validate legacy query fields; carry the selection explicitly."),
    "/api/v1/issues/{issue_no}": (
        "Read the exact Issue summary, then pass its id as issue_id to independent "
        "bounded changes/candidates/assessments pages. Use full counts and limit/offset."),
    "/api/v1/issues/{issue_no}/impact": (
        "Read the Issue summary; use its id as issue_id for bounded candidates and "
        "complete assessment history. Candidate software membership is review scope, "
        "not inferred impact or permission. Select an exact release and frozen snapshot."),
    "/api/v1/issues/{issue_no}/impact/{release_id}": (
        "Read the exact impact summary with optional snapshot_id selection. Pass "
        "its issue_id and snapshot_id to bounded components/verification pages. "
        "For a historical judgment, select its recorded snapshot_id, not the latest. "
        "Preserve none sentinels and exact frozen execution scope; no bulk fallback."),
    "/api/v1/issues/{issue_no}/impact-assessments": (
        "Read the exact Issue summary, then use its id as issue_id for the assessment "
        "page with limit/offset and full totals. This replaces the old truncated head "
        "with navigable complete history. Review each judgment's recorded snapshot_id."),
    "/api/v1/deployments/{deployment_no}": (
        "Read the exact deployment profile; filter changeover and batch catalogs by "
        "deployment_id=profile.id. Use limit/offset and full history_counts. "
        "Recorded states and counts do not authorize production."),
    "/api/v1/deployments/{deployment_no}/provenance": (
        "Read the exact deployment profile. If provenance.delivery exists, filter "
        "the decision catalog by both its release_id and snapshot_id; otherwise no "
        "decision scope is inferred. Use limit/offset; do not use the deployment's "
        "current actual software as the delivered decision scope."),
    "/api/v1/deliveries/{package_no}": (
        "Use the delivery catalog to select an exact package_no, revision and stored "
        "UUID; q is a literal substring filter, not an exact identity check. Then "
        "read /api/v1/deliveries/{package_no}/revisions/{revision}/profile. "
        "No latest revision or substitute delivery is selected automatically."),
    "/api/v1/deliveries/{package_no}/revisions/{revision}": (
        "Read the exact revision profile and its bounded artifacts endpoint. "
        "Filter the distribution catalog by delivery_package_id=profile.id. "
        "Preserve exact revision identity, full history_counts and limit/offset."),
    "/api/v1/distributions/{distribution_no}": (
        "Read the exact distribution profile; filter the authorization catalog by "
        "distribution_id=profile.id. Use limit/offset and full history_counts."),
    "/api/v1/authorizations/{authorization_no}": (
        "Read the exact authorization profile; filter deployment and batch catalogs "
        "by authorization_id=profile.id. Use limit/offset and full history_counts. "
        "Recorded batch counts are not remaining capacity or production permission."),
}


def _endpoint(path: str, replacements: tuple[str, ...], pin: str | None):
    async def retired(request: Request):
        identifier = next(iter(request.path_params.values()), "")
        parameters = {"identifier": identifier, **request.path_params}
        urls = list(replacements)
        for key, value in parameters.items():
            urls = [url.replace("{" + key + "}", quote(str(value), safe="")) for url in urls]
        content = {
            "detail": "legacy_read_retired",
            "retired_route": path,
            "replacements": urls,
            "required_collection_pin": pin,
            "instructions": MIGRATION_INSTRUCTIONS.get(path) or (
                f"Read the summary first, then pass its id as {pin} to the bounded collection; "
                "use limit/offset and complete summary counts."
                if pin else "Use the bounded catalog with limit/offset and complete filtered counts."
            ),
        }
        return JSONResponse(status_code=410, content=content,
                            headers={"Link": f'<{urls[0]}>; rel="successor-version"',
                                     "Cache-Control": "no-store"})
    return retired


for index, (path, replacements, pin) in enumerate(RETIRED_READS):
    router.add_api_route(path, _endpoint(path, replacements, pin), methods=["GET"],
                         name=f"retired_compatibility_read_{index}", deprecated=True,
                         status_code=410, response_class=JSONResponse,
                         summary="Retired legacy read; use bounded successor",
                         responses={410: {"description": "Legacy read retired; successor URLs and required UUID pin returned"}})
