"""请求级日志摘要上下文。

默认只保存可安全落盘的摘要字段（工具名、业务码、状态、DTC 数量、异常类型）。
显式开启请求体日志时，可额外保存已经紧凑序列化并限长的 JSON 字符串；
不保存原始 Python 对象、上游返回对象或任何请求 Header。

生命周期由 app.main 的 middleware 管理：请求进入时创建，请求结束输出完成日志后重置。
endpoint 与异常处理器通过 current_log_context() 就地更新字段，
同一个 dataclass 实例在线程池 handler 中也可见（ContextVar 复制的是对象引用）。
"""
from contextvars import ContextVar
from dataclasses import dataclass

# 请求完成日志的状态取值（设计 §8.2）
STATUS_SUCCESS = "success"
STATUS_VALIDATION_ERROR = "validation_error"
STATUS_TOOL_NOT_FOUND = "tool_not_found"
STATUS_UPSTREAM_ERROR = "upstream_error"
STATUS_INTERNAL_ERROR = "internal_error"


@dataclass
class RequestLogContext:
    """一次 HTTP 请求的日志上下文，只允许存放白名单及已受控的请求体字段。"""

    tool_name: str | None = None
    business_code: int | None = None
    status: str = STATUS_SUCCESS
    dtc_count: int | None = None
    error_type: str | None = None
    request_body: str | None = None
    request_body_status: str | None = None
    request_body_truncated: bool = False


request_log_ctx: ContextVar[RequestLogContext | None] = ContextVar("request_log", default=None)


def current_log_context() -> RequestLogContext | None:
    """返回当前请求的日志上下文；无 HTTP 请求上下文（启动、后台任务）时为 None。"""
    return request_log_ctx.get()
