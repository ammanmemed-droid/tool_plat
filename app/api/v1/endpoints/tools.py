"""Agent 侧工具发现与统一调用端点。"""
from typing import Annotated

from fastapi import APIRouter, Path

from app.api.v1.schemas import (
    ToolDetailResponse,
    ToolInvokeRequest,
    ToolInvokeResponse,
    ToolListResponse,
)
from app.core.logging_config import get_app_logger
from app.core.openapi import COMMON_RESPONSES
from app.core.registry import tool_registry
from app.core.responses import success

logger = get_app_logger(__name__)

router = APIRouter(prefix="/tools", tags=["tools"])


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
                    },
                },
            },
        },
        **COMMON_RESPONSES,
    },
)
def invoke_tool(
    tool_name: Annotated[str, Path(description="工具名称，如 dtc_context_service")],
    request: ToolInvokeRequest,
) -> ToolInvokeResponse:
    """按 tool-schema.json 校验入参，执行 handler，校验出参后返回结果。"""
    logger.info("invoke_tool: tool_name=%s, arguments=%s", tool_name, request.arguments)
    result = tool_registry.invoke(tool_name, request.arguments)
    logger.info("invoke_tool: tool_name=%s, result=%s", tool_name, result)
    return success(data=result)
