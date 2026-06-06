"""
SENOVA AI Dashboard — FastAPI entry point.

Starts Uvicorn with CORS configured for the local Vite dev server.
All business logic lives in `services/` and `api/routes/`.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import ALLOWED_ORIGINS
from app.api.routes import upload, analytics
from app.api.routes.analytics import analytics_router

app = FastAPI(
    title="SENOVA AI Dashboard API",
    version="0.1.0",
    description="Retail analytics engine for garment / sales & inventory data.",
)

# ----------------------------------------------------------------
# CORS — allow Vite dev server to call the API without a proxy.
# ----------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------
# Routers — each route group lives in its own file under api/routes/
# ----------------------------------------------------------------
app.include_router(upload.router, prefix="/upload", tags=["Upload"])
app.include_router(analytics.router, prefix="/process", tags=["Analytics"])
app.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])


@app.get("/health")
def health_check():
    """Lightweight liveness probe for container orchestration / monitoring."""
    return {"status": "ok"}
