"""Routers. Everything is protected unless it is listed as public here; tests enforce this for every route."""
from fastapi import APIRouter, Depends

from . import auth, chat, evidence, health, library, requirements, models
from .deps import current_user

api_router = APIRouter(prefix="/api")

# Public: liveness, and the login that issues a token.
api_router.include_router(health.router)
api_router.include_router(auth.public)

# Everything else needs a signed-in user.
protected = APIRouter(dependencies=[Depends(current_user)])
protected.include_router(auth.private)
protected.include_router(evidence.router)
protected.include_router(library.router)
protected.include_router(chat.router)
protected.include_router(requirements.router)
protected.include_router(models.router)
api_router.include_router(protected)
