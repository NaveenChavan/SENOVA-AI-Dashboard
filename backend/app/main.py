"""
SENOVA AI Dashboard — FastAPI entry point.

Starts Uvicorn with CORS configured for the local Vite dev server.
All business logic lives in `services/` and `api/routes/`.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import ALLOWED_ORIGINS, UPLOAD_SWEEP_INTERVAL_MINUTES
from app.api.routes import upload, analytics
from app.api.routes.analytics import analytics_router
from app.services.file_handler import sweep_expired_uploads

logger = logging.getLogger("senova.uploads")


async def _sweep_loop() -> None:
    """Background task: periodically remove expired uploads from disk."""
    interval_seconds = UPLOAD_SWEEP_INTERVAL_MINUTES * 60
    while True:
        try:
            removed = sweep_expired_uploads()
            if removed:
                logger.info("Upload sweep removed %d expired file(s).", removed)
        except Exception:
            logger.exception("Upload sweep failed.")
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run once on startup so leftover files from a previous run are cleared
    # immediately, then keep sweeping on an interval for the app's lifetime.
    sweep_expired_uploads()
    task = asyncio.create_task(_sweep_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(
    title="SENOVA AI Dashboard API",
    version="0.1.0",
    description="Retail analytics engine for garment / sales & inventory data.",
    lifespan=lifespan,
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
