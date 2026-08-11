"""API v1 OpenAPI / Swagger 模型定义。"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.responses import ApiResponse


class HealthData(BaseModel):
    status: Literal["UP"] = Field(description="服务健康状态")


class HealthResponse(ApiResponse):
    data: HealthData | None = Field(default=None, description="健康检查数据")


class ToolSummary(BaseModel):
    tool_name: str = Field(description="工具唯一名称")
    tool_kind: str = Field(description="工具类型，如 global_tool_service")
    description: str = Field(description="工具用途说明")
    skill_name: str = Field(description="来源 Skill 目录名")


class ToolDetail(ToolSummary):
    input_schema: dict[str, Any] = Field(description="入参 JSON Schema（来自 tool-schema.json）")
    output_schema: dict[str, Any] = Field(description="出参 JSON Schema（来自 tool-schema.json）")


class ToolListResponse(ApiResponse):
    data: list[ToolSummary] | None = Field(default=None, description="可用工具摘要列表")


class ToolDetailResponse(ApiResponse):
    data: ToolDetail | None = Field(default=None, description="工具完整契约")


class ToolInvokeRequest(BaseModel):
    """统一调用请求体。arguments 须满足该工具 input_schema。"""

    model_config = ConfigDict(extra="allow", json_schema_extra={
        "examples": [
            {
                "arguments": {
                    "brand": "丰田",
                    "model": "汉兰达",
                    "year": 2021,
                    "dtc_codes": ["P0136", "P0137", "P0138", "P0420"],
                    "language": "en",
                },
            },
            {
                "arguments": {
                    "brand": "丰田",
                    "model": "汉兰达",
                    "year": 2021,
                    "dtc_codes": ["P0136", "P0137", "P0138"],
                    "language": "en",
                },
            },
            {
                "brand": "Toyota",
                "dtc_codes": ["P0420", "P0430"],
                "model": "Highlander",
            },
        ],
    })

    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="工具入参对象，字段须满足 GET /tools/{tool_name} 返回的 input_schema",
    )

    @model_validator(mode="before")
    @classmethod
    def merge_flat_payload(cls, data: Any) -> Any:
        """兼容 Agent 直接将工具字段放在请求体顶层、省略 arguments 包裹的写法。"""
        if not isinstance(data, dict):
            return data
        arguments = data.get("arguments")
        if isinstance(arguments, dict) and arguments:
            return data
        flat = {key: value for key, value in data.items() if key != "arguments"}
        if flat:
            return {"arguments": flat}
        return data


class ToolInvokeResponse(ApiResponse):
    data: dict[str, Any] | None = Field(default=None, description="工具执行结果，结构须满足 output_schema")


class ErrorResponse(ApiResponse):
    """错误响应信封（code != 0）。"""

    code: int = Field(description="业务错误码，如 40000 入参校验失败、40400 工具不存在")
    message: str = Field(description="错误说明")
    data: None = None
