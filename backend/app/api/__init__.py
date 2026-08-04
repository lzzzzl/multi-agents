"""API 路由集合。"""

from fastapi import APIRouter

from app.api import health, runs, tasks

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(tasks.router)
api_router.include_router(runs.router)

__all__ = ["api_router"]
