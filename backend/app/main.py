from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.releases import router as releases_router
from app.api.dashboard import router as dashboard_router
from app.api.approvals import router as approvals_router
from app.api.distribution import router as distribution_router
from app.api.production import router as production_router
from app.core.config import settings
from app.core.db import engine

APP_VERSION = "0.7.0"

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
