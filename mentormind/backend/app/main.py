from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from mentormind.backend.app.routers import (
    assistant,
    documents,
    health,
    ingest,
    jobs,
    media,
    nn,
    profiles,
    qnn,
    rca,
    sigma,
    videos,
)
from mentormind.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="MentorMind Know-How AI REST API (Spec 08)",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(profiles.router)
app.include_router(nn.router)
app.include_router(qnn.router)
app.include_router(media.router)
app.include_router(jobs.router)
app.include_router(ingest.router)
app.include_router(documents.router)
app.include_router(videos.router)
app.include_router(assistant.router)
app.include_router(rca.router)
app.include_router(sigma.router)

# Railway / production: serve the built React application from the same origin as the API.
# API routes are registered first, so they keep precedence over the root static mount.
_frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
