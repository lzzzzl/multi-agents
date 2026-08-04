"""API 路由集合。"""

from fastapi import APIRouter

from app.api import artifacts, health, runs, tasks

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(tasks.router)
api_router.include_router(runs.router)
api_router.include_router(artifacts.router)

__all__ = ["api_router"]
