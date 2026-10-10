"""FastAPI application. Run from the repo root:  make backend   (or: uvicorn app.main:app --reload --app-dir backend)"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import api_router
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    # Interactive docs describe every endpoint: off when APP_ENV=production.
    docs = None if settings.production else "/docs"
    app = FastAPI(title="Requirement Evidence Engine", version=__version__, docs_url=docs,
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
