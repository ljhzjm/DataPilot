from fastapi import APIRouter

from app.api.routes import artifacts, conversations, datasets, health, observability

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(conversations.router)
api_router.include_router(datasets.router)
api_router.include_router(observability.router)
api_router.include_router(artifacts.router)
