from app.api.compatibility_reads import router as compatibility_reads_router
from app.api.manufacturing_views import router as manufacturing_views_router
from app.api.organization_views import router as organization_views_router
from app.api.issue_views import router as issue_views_router
from app.api.change_views import router as change_views_router
from app.api.change_coverage_views import router as change_coverage_views_router
from app.api.change_catalog import router as change_catalog_router
from app.api.release_catalog import router as release_catalog_router
from app.api.asr_readiness import router as asr_readiness_router
from app.api.asr_passport import router as asr_passport_router
from app.api.snapshot_comparison_views import router as snapshot_comparison_views_router
from app.api.snapshot_views import router as snapshot_views_router
from app.api.asr_policy import router as asr_policy_router
from app.api.asr_components import router as asr_components_router
from app.api.standard_release_views import router as standard_views_router
from app.api.asr_evidence import router as asr_evidence_router
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.api.releases import router as releases_router
from app.api.dashboard import router as dashboard_router
from app.api.approvals import router as approvals_router
from app.api.distribution import router as distribution_router
from app.api.production import router as production_router
from app.api.activity import router as activity_router
from app.api.search import router as search_router
from app.api.organizations import router as organizations_router
from app.api.impact import router as impact_router
from app.api.snapshots import router as snapshots_router
from app.api.release_matrix import router as release_matrix_router
from app.api.change_coverage import router as change_coverage_router
from app.api.dvp_catalog import router as dvp_catalog_router
from app.api.testing_releases import router as test_releases_router
from app.api.resources import router as resources_router
from app.api.distribution_catalog import router as distribution_catalog_router
from app.api.production_catalog import router as production_catalog_router
from app.api.governance_catalog import router as governance_catalog_router
from app.core.config import settings
from app.core.db import engine
from app.auth import AuthenticationError, authenticate_write_request
from app.authorization import AuthorizationError

APP_VERSION = "0.18.22"

app = FastAPI(title="SoftwareLifeCycle API", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(AuthorizationError)
async def authorization_error_handler(_request: Request, exc: AuthorizationError):
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": str(exc)},
    )
app.include_router(releases_router, prefix="/api/v1")
app.include_router(dashboard_router)
app.include_router(release_catalog_router)
app.include_router(change_catalog_router)
app.include_router(issue_views_router)
app.include_router(change_views_router)
app.include_router(change_coverage_views_router)
app.include_router(asr_evidence_router)
app.include_router(standard_views_router)
app.include_router(asr_components_router)
app.include_router(asr_policy_router)
app.include_router(asr_passport_router)
app.include_router(asr_readiness_router)
app.include_router(approvals_router)
app.include_router(distribution_router)
app.include_router(production_router)
app.include_router(activity_router)
app.include_router(search_router)
app.include_router(organizations_router)
app.include_router(compatibility_reads_router)
app.include_router(organization_views_router)
app.include_router(manufacturing_views_router)
app.include_router(impact_router)
app.include_router(snapshot_comparison_views_router)
app.include_router(snapshot_views_router)
app.include_router(snapshots_router)
app.include_router(release_matrix_router)
app.include_router(change_coverage_router)
app.include_router(dvp_catalog_router)
app.include_router(test_releases_router)
app.include_router(resources_router)
app.include_router(distribution_catalog_router)
app.include_router(production_catalog_router)
app.include_router(governance_catalog_router)


@app.middleware("http")
async def read_only_guard(request: Request, call_next):
    is_write = request.method not in {"GET", "HEAD", "OPTIONS"}
    if settings.read_only_mode and is_write:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "read_only_mode"},
        )
    if is_write and settings.auth_mode == "oidc":
        try:
            await run_in_threadpool(authenticate_write_request, request, settings)
        except AuthenticationError as exc:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": str(exc)},
                headers={"WWW-Authenticate": "Bearer"},
            )
    return await call_next(request)

@app.get("/health")
def health():
    return {"status": "ok", "version": APP_VERSION}


@app.get("/health/live")
def liveness():
    return {"status": "ok", "version": APP_VERSION}


@app.get("/health/ready")
def readiness():
    try:
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
    except SQLAlchemyError:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "reason": "database_unavailable"},
        )

    if revision != settings.required_db_revision:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "reason": "database_revision_mismatch",
                "database_revision": revision,
                "required_revision": settings.required_db_revision,
            },
        )

    return {
        "status": "ready",
        "version": APP_VERSION,
        "database_revision": revision,
    }
