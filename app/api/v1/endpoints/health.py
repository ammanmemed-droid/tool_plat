"""健康检查端点（供 Nacos / 负载均衡探活）。"""
from fastapi import APIRouter

from app.api.v1.schemas import HealthResponse
from app.core.responses import success

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="健康检查",
    response_model=HealthResponse,
    responses={200: {"description": "服务正常运行"}},
)
def health() -> HealthResponse:
    """返回服务 UP 状态，响应格式与其他 API 一致（含 trace_id）。"""
    return success(data={"status": "UP"})
