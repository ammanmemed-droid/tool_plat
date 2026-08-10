"""roxie-rag-service 原生 REST 接口透传端点。

与工具调用（/tools/{tool_name}/invoke）的区别：
- 工具调用按本中台 tool-schema.json 校验入参/出参，响应包装为统一信封；
- 本端点不做任何参数改写与出参校验，请求体按上游原接口契约原样转发，
  上游业务响应原样返回（非信封），便于已有调用方零改动迁移。
"""
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.services.rag_client import rag_client

router = APIRouter(tags=["rag-proxy"])


def _forward(proxy_name: str, upstream_path: str, payload: dict[str, Any]) -> JSONResponse:
    """按原接口契约把请求体转发到 roxie-rag-service，业务响应原样返回。"""
    settings = get_settings()
    result = rag_client.invoke(
        proxy_name,
        upstream_path,
        payload,
        service_name=settings.rag_service_name,
        base_path=settings.diagnose_base_path,
        timeout=settings.diagnose_timeout,
    )
    return JSONResponse(content=result)


@router.post(
    "/diagnoses",
    summary="DTC 综合诊断检索（原样透传 roxie-rag-service）",
    description=(
        "请求体遵循 roxie-rag-service `POST /api/v1/diagnoses` 原接口契约"
        "（query、vehicle_info、top_n、enable_reranker 等），本中台原样转发，"
        "上游业务响应原样返回。"
    ),
    response_class=JSONResponse,
)
def diagnoses_proxy(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    """将请求体原样转发到 roxie-rag-service 的 /api/v1/diagnoses。"""
    return _forward("diagnoses", "diagnoses", payload)


@router.post(
    "/dtc-cause-cards",
    summary="DTC 故障组原因处置卡片聚合（原样透传 roxie-rag-service）",
    description=(
        "请求体遵循 roxie-rag-service `POST /api/v1/dtc-cause-cards` 原接口契约"
        "（brand、model、dtc_codes、vehicle_match_policy 等），本中台原样转发，"
        "上游业务响应原样返回。"
    ),
    response_class=JSONResponse,
)
def dtc_cause_cards_proxy(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    """将请求体原样转发到 roxie-rag-service 的 /api/v1/dtc-cause-cards。"""
    return _forward("dtc-cause-cards", "dtc-cause-cards", payload)
