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


def _endpoint(path: str, replacements: tuple[str, ...], pin: str | None):
    async def retired(request: Request):
        identifier = next(iter(request.path_params.values()), "")
        urls = [url.replace("{identifier}", quote(str(identifier), safe="")) for url in replacements]
        content = {
            "detail": "legacy_read_retired",
            "retired_route": path,
            "replacements": urls,
            "required_collection_pin": pin,
            "instructions": (
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
