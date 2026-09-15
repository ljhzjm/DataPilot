from fastapi import APIRouter

from app.api.routes import conversations, datasets, health

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(conversations.router)
api_router.include_router(datasets.router)
