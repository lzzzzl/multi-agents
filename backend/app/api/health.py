"""健康检查。"""


from fastapi import APIRouter

from app.schemas.common import ApiResponse, HealthResponse

router = APIRouter()


@router.get("/health", response_model=ApiResponse[HealthResponse])
def health() -> ApiResponse:
    return ApiResponse.ok({"status": "ok"})
