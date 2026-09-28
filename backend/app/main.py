from fastapi import FastAPI
from app.api.releases import router as releases_router

app = FastAPI(title="SoftwareLifeCycle API", version="0.1.0")
app.include_router(releases_router, prefix="/api/v1")

@app.get("/health")
def health(): return {"status": "ok"}
