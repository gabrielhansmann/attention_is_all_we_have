"""FastAPI application. Run from the repo root:  make backend   (or: uvicorn app.main:app --reload --app-dir backend)"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import api_router
from app.config import get_settings


log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """On start, continue the runs a restart interrupted (decision 0019). Never blocks or breaks startup."""
    if get_settings().db_url:
        try:
            from app.api import deps
            from app.orchestration import loop
            loop.resume_unfinished(deps._connect, deps.get_orchestrator(), deps.get_runners())
        except Exception:
            log.exception("could not resume unfinished runs")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    # Interactive docs describe every endpoint: off when APP_ENV=production.
    docs = None if settings.production else "/docs"
    app = FastAPI(title="Requirement Evidence Engine", version=__version__, docs_url=docs, lifespan=lifespan,
                  redoc_url=None, openapi_url=None if settings.production else "/openapi.json")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    return app


app = create_app()
