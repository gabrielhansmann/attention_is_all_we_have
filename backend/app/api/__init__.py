from fastapi import APIRouter

from . import chat, evidence, health

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(evidence.router)
api_router.include_router(chat.router)
