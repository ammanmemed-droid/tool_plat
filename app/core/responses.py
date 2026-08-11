"""统一响应信封，便于 Agent 以固定格式消费结果。"""
import uuid
from contextvars import ContextVar
from typing import Any

from pydantic import BaseModel, Field

trace_id_ctx: ContextVar[str | None] = ContextVar("trace_id", default=None)
EchoValue = str | int
echo_ctx: ContextVar[dict[str, EchoValue]] = ContextVar("echo", default={})


def is_echo_id_key(field_name: str) -> bool:
    """判断顶层字段是否属于 Agent 关联 ID。"""
    return field_name == "id" or field_name.endswith("_id")


def extract_echo_ids(payload: object) -> dict[str, EchoValue]:
    """从请求体顶层提取可安全回显的标量 ID，不递归扫描。"""
    if not isinstance(payload, dict):
        return {}
    return {
        key: value
        for key, value in payload.items()
        if isinstance(key, str)
        and is_echo_id_key(key)
        and value is not None
        and not isinstance(value, bool)
        and isinstance(value, (str, int))
    }


class ApiResponse(BaseModel):
    code: int = Field(default=0, description="业务码，0 表示成功")
    message: str = Field(default="success", description="结果说明")
    data: Any = Field(default=None, description="业务数据")
    trace_id: str = Field(default_factory=lambda: trace_id_ctx.get() or uuid.uuid4().hex, description="链路追踪 ID")


def success(data: Any = None, message: str = "success") -> ApiResponse:
    return ApiResponse(code=0, message=message, data=data)


def error(code: int, message: str) -> ApiResponse:
    return ApiResponse(code=code, message=message, data=None)
