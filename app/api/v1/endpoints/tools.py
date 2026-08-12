"""Agent 侧工具发现与统一调用端点。"""
from copy import deepcopy
from typing import Annotated, Any

from fastapi import APIRouter, Path

from app.api.v1.schemas import (
    ToolDetailResponse,
    ToolInvokeRequest,
    ToolInvokeResponse,
    ToolListResponse,
)
from app.core.log_context import current_log_context
from app.core.openapi import COMMON_RESPONSES
from app.core.registry import tool_registry
from app.core.responses import success

router = APIRouter(prefix="/tools", tags=["tools"])

INVOKE_RESPONSES = deepcopy(COMMON_RESPONSES)
for response_spec in INVOKE_RESPONSES.values():
    response_spec["content"]["application/json"]["example"]["echo"] = {}


@router.get(
    "",
    summary="工具发现：列出全部可用工具",
    response_model=ToolListResponse,
    responses={200: {"description": "成功返回工具摘要列表"}},
)
def list_tools() -> ToolListResponse:
    """返回当前已注册的全部工具摘要（tool_name / description / skill_name）。"""
    return success(data=tool_registry.list_tools())


@router.get(
    "/{tool_name}",
    summary="工具发现：获取单个工具完整契约",
    response_model=ToolDetailResponse,
    responses={**COMMON_RESPONSES},
)
def get_tool(
    tool_name: Annotated[str, Path(description="工具名称，如 dtc_context_service")],
) -> ToolDetailResponse:
    """返回指定工具的完整契约，含 input_schema 与 output_schema，供 Agent 组织入参。"""
    return success(data=tool_registry.get_tool(tool_name).detail())


@router.post(
    "/{tool_name}/invoke",
    summary="统一调用：执行指定工具",
    response_model=ToolInvokeResponse,
    responses={
        200: {
            "description": "工具执行成功",
            "content": {
                "application/json": {
                    "example": {
                        "code": 0,
                        "message": "success",
                        "data": {
                            "contexts": [
                                {
                                    "dtc_code": "P0136",
                                    "match_level": "year_fallback",
                                    "dtc_description": "氧传感器电路故障",
                                    "dtc_category": "动力系统",
                                    "trigger_conditions": [],
                                    "related_parts": ["后氧传感器"],
                                    "related_datastreams": ["氧传感器电压"],
                                }
                            ],
                            "issues": [],
                        },
                        "trace_id": "a1b2c3d4e5f6",
                        "echo": {
                            "request_id": "req-001",
                            "session_id": "session-001",
                        },
                    },
                },
            },
        },
        **INVOKE_RESPONSES,
    },
)
def invoke_tool(
    tool_name: Annotated[str, Path(description="工具名称，如 dtc_context_service")],
    request: ToolInvokeRequest,
) -> ToolInvokeResponse:
    """按 tool-schema.json 校验入参，执行 handler，校验出参后返回结果。"""
    log_ctx = current_log_context()
    if log_ctx is not None:
        # 只写工具名与 DTC 数量，请求参数与执行结果一律不进日志
        log_ctx.tool_name = tool_name
        log_ctx.dtc_count = _dtc_count(request.arguments)
    return ToolInvokeResponse(data=tool_registry.invoke(tool_name, request.arguments))


def _dtc_count(arguments: dict[str, Any]) -> int | None:
    """从已解析入参统计 DTC 数量，不保留任何 DTC 内容。"""
    codes = arguments.get("dtc_codes")
    if isinstance(codes, list):
        return len(codes)
    if isinstance(arguments.get("dtc_code"), str):
        return 1
    return None
