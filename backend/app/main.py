"""FastAPI application. Run from the repo root:  make backend   (or: uvicorn app.main:app --reload --app-dir backend)"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import api_router
from app.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="Requirement Evidence Engine", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    return app


app = create_app()
