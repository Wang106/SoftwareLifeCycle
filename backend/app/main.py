from fastapi import FastAPI
from app.api.releases import router as releases_router
from app.api.dashboard import router as dashboard_router

app = FastAPI(title="SoftwareLifeCycle API", version="0.2.0")
app.include_router(releases_router, prefix="/api/v1")
app.include_router(dashboard_router)

@app.get("/health")
def health():
    return {"status": "ok"}
