from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.releases import router as releases_router
from app.api.dashboard import router as dashboard_router
from app.core.config import settings

app = FastAPI(title="SoftwareLifeCycle API", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(releases_router, prefix="/api/v1")
app.include_router(dashboard_router)

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.3.0"}
