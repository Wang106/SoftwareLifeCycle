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

# Exact Snapshot manifests and comparison graphs use bounded successors.
RETIRED_READS += (
    ("/api/v1/snapshots/{snapshot_no}",
     ("/api/v1/snapshots/{snapshot_no}/summary", "/api/v1/snapshots/{snapshot_no}/artifacts",
      "/api/v1/snapshots/{snapshot_no}/rules"), "snapshot_id"),
    ("/api/v1/snapshots/{snapshot_no}/compare/{target_no}",
     ("/api/v1/snapshots/{snapshot_no}/comparison/{target_no}/summary",
      "/api/v1/snapshots/{snapshot_no}/comparison/{target_no}/files"), None),
)

RETIRED_READS += (
    ("/api/v1/testing/dvp", ("/api/v1/testing/dvp/catalog",), None),
    ("/api/v1/testing/dvp/id/{item_id}",
     ("/api/v1/testing/dvp/id/{item_id}/profile",
      "/api/v1/testing/dvp/id/{item_id}/relations/criteria",
      "/api/v1/testing/dvp/id/{item_id}/relations/points",
      "/api/v1/testing/dvp/id/{item_id}/relations/issues",
      "/api/v1/testing/dvp/id/{item_id}/executions"), "dvp_item_id"),
)

RETIRED_READS += (
    ("/api/v1/approvals", ("/api/v1/governance/approvals",), None),
    ("/api/v1/approvals/{approval_no}",
     ("/api/v1/governance/approvals/{approval_no}/summary",
      "/api/v1/governance/approvals/{approval_no}/steps",
      "/api/v1/governance/approvals/{approval_no}/actions"), "approval_id"),
    ("/api/v1/activity", ("/api/v1/audit/events",), None),
)

# Release/ASR candidates: retain three audited scalar reads; retire rich/preview reads.
RETIRED_READS += (
    ("/api/v1/releases", ("/api/v1/release-catalog/standard", "/api/v1/release-catalog/application"), None),
    ("/api/v1/releases/standard", ("/api/v1/release-catalog/standard",), None),
    ("/api/v1/releases/standard/id/{release_id}",
     ("/api/v1/releases/standard/id/{release_id}/summary",
      "/api/v1/releases/standard/id/{release_id}/components",
      "/api/v1/releases/standard/id/{release_id}/applications"), None),
    ("/api/v1/releases/application", ("/api/v1/release-catalog/application",), None),
    ("/api/v1/releases/application/id/{release_id}/decision",
     ("/api/v1/releases/application/id/{release_id}/passport/summary",
      "/api/v1/governance/decisions?release_id={release_id}"), None),
    ("/api/v1/releases/application/id/{release_id}/decisions",
     ("/api/v1/governance/decisions?release_id={release_id}",), None),
    ("/api/v1/releases/application/id/{release_id}/components",
     ("/api/v1/releases/application/id/{release_id}/components/summary",
      "/api/v1/releases/application/id/{release_id}/components/declarations",
      "/api/v1/releases/application/id/{release_id}/components/unlinked-base"), None),
    ("/api/v1/releases/application/id/{release_id}/evidence",
     ("/api/v1/releases/application/id/{release_id}/evidence-summary",
      "/api/v1/releases/application/id/{release_id}/evidence/artifacts",
      "/api/v1/releases/application/id/{release_id}/evidence/executions"), "snapshot_id"),
    ("/api/v1/releases/application/id/{release_id}/snapshot-policy",
     ("/api/v1/releases/application/id/{release_id}/snapshot-policy/summary",
      "/api/v1/releases/application/id/{release_id}/snapshot-policy/artifacts",
      "/api/v1/releases/application/id/{release_id}/snapshot-policy/rules"), "snapshot_id"),
    ("/api/v1/releases/application/id/{release_id}/downstream",
     ("/api/v1/releases/application/id/{release_id}/downstream-summary",
      "/api/v1/distribution/catalog/deliveries?release_id={release_id}",
      "/api/v1/production/catalog/deployments?authorization_release_id={release_id}"), None),
    ("/api/v1/releases/application/id/{release_id}/readiness",
     ("/api/v1/releases/application/id/{release_id}/readiness/summary",
      "/api/v1/releases/application/id/{release_id}/readiness/exceptions"), "snapshot_id"),
) + tuple(
    (f"/api/v1/releases/application/{{version}}/{kind}",
     ("/api/v1/release-catalog/application/resolve?identifier={version}",), None)
    for kind in ('overview', 'verification', 'artifacts', 'readiness', 'decision')
)

MIGRATION_INSTRUCTIONS = {
    "/api/v1/approvals/{approval_no}": (
        "Read the exact approval summary; pass its id as approval_id to independent "
        "steps/actions pages with limit/offset and complete counts. Preserve the "
        "original release and Snapshot binding; do not substitute the latest. "
        "Recorded approval actions are separate from formal release decisions; "
        "a visible pending step is not authority or permission to execute."),
    "/api/v1/activity": (
        "Use the audit catalog with strict exact identity/time filters and limit/offset. "
        "Read /api/v1/activity/{event_no} for an exact event payload. Preserve actor "
        "principal identity separately from declared actor names; no truncated head "
        "or inferred latest release selection."),
    "/api/v1/testing/dvp/id/{item_id}": (
        "Read the exact item profile; pass its id as dvp_item_id to independent "
        "criteria/points/issues pages with limit/offset and complete relation_counts. "
        "Execution history uses limit/before_number, explicit release_id and optional "
        "historical snapshot_no. Preserve recorded contexts; an earlier PASS does "
        "not verify a later Snapshot. Carry legacy selections explicitly."),
    "/api/v1/snapshots/{snapshot_no}": (
        "Read the exact frozen Snapshot summary; pass its id as snapshot_id to "
        "independent artifacts/rules pages with limit/offset and full counts. "
        "Preserve historical Snapshot selection; never substitute the latest."),
    "/api/v1/snapshots/{snapshot_no}/compare/{target_no}": (
        "Read the exact comparison summary; pass source.id as source_id and "
        "target.id as target_id to the bounded files page. Preserve both historical "
        "Snapshot identities, same-release validation and full difference counts; "
        "use show, limit/offset without replacing either Snapshot with the latest."),
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


# Old version identifiers never acquire an invented UUID or a silent latest choice.
for kind in ('overview', 'verification', 'artifacts', 'readiness', 'decision'):
    MIGRATION_INSTRUCTIONS[f"/api/v1/releases/application/{{version}}/{kind}"] = (
        "Resolve the exact identifier first; missing/ambiguous results require explicit "
        "release selection. Use the resolved stored UUID with bounded profile, components, "
        "evidence, readiness and passport summaries/children. Read selected Snapshot "
        "identity before collection pages. Current working artifact/policy aggregates "
        "come from readiness; frozen files/rules come from snapshot-policy. They are "
        "different evidence scopes. Review exact formal decision history, not an "
        "inferred current approval or latest substitute.")
MIGRATION_INSTRUCTIONS.update({
    "/api/v1/releases/standard/id/{release_id}": "Read exact SSR summary; use its UUID in the components/applications path and verify returned release_id. Use limit/offset and full totals; do not invent an unsupported query pin.",
    "/api/v1/releases/application/id/{release_id}/components": "Read exact component summary; use the stored release UUID in independent declarations/unlinked-base paths, verify returned release_id/base_release_id (including none), and use limit/offset. These pages do not accept extra query UUID pins. No inheritance or approval is inferred.",
    "/api/v1/releases/application/id/{release_id}/evidence": "Read evidence summary with an optional historical snapshot_id selection; pin the returned Snapshot UUID for bounded artifacts/executions pages and complete counts. Preserve historical scope and never replace it with latest results.",
    "/api/v1/releases/application/id/{release_id}/snapshot-policy": "Read frozen-policy summary with optional historical snapshot_id; use its exact Snapshot UUID for independent artifact/rule pages. Frozen rules are distinct from current working policy; no latest substitution.",
    "/api/v1/releases/application/id/{release_id}/decision": "Read paired passport summary and bounded formal decision history scoped by exact release_id and, when selected, snapshot_id. A recorded head is not release permission or the current Snapshot's approval.",
    "/api/v1/releases/application/id/{release_id}/decisions": "Use bounded formal decision history with exact release_id and optional snapshot_id; preserve recorded original bindings, limit/offset and full totals.",
    "/api/v1/releases/application/id/{release_id}/downstream": "Read downstream summary; distribution catalogs use exact release_id and production catalogs use authorization_release_id. Counts follow the recorded parent chain, not current actual release membership or permission. Preserve independent full histories.",
    "/api/v1/releases/application/id/{release_id}/readiness": "Read current readiness summary, then pin its snapshot_id (or none) for approved-exception pages. A stale current pin fails closed; historical evidence belongs to separately selected frozen evidence, not an inferred historical readiness judgment.",
})


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
