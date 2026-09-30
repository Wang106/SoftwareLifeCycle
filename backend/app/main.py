from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

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
from app.core.config import settings
from app.core.db import engine

APP_VERSION = "0.8.0"

app = FastAPI(title="SoftwareLifeCycle API", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(releases_router, prefix="/api/v1")
app.include_router(dashboard_router)
app.include_router(approvals_router)
app.include_router(distribution_router)
app.include_router(production_router)
app.include_router(activity_router)
app.include_router(search_router)
app.include_router(organizations_router)
app.include_router(impact_router)
app.include_router(snapshots_router)
app.include_router(release_matrix_router)
app.include_router(change_coverage_router)
app.include_router(dvp_catalog_router)
app.include_router(test_releases_router)
app.include_router(resources_router)
app.include_router(distribution_catalog_router)
app.include_router(production_catalog_router)


@app.middleware("http")
async def read_only_guard(request: Request, call_next):
    if settings.read_only_mode and request.method not in {"GET", "HEAD", "OPTIONS"}:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "read_only_mode"},
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
