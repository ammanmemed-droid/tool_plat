"""Roxie Tool 中台入口。

启动流程：
1. 导入 app.tools 触发各工具 @register_tool 自注册（注册 handler）
2. 扫描 myskills/*/tool-schema.json 加载契约并绑定
3. 注册到 Nacos 并启动心跳
4. 关闭时从 Nacos 注销
"""
import logging
import time
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse

import app.tools  # noqa: F401 - 导入即完成工具自注册
from app.api.v1.router import api_router
from app.config import get_settings
from app.core.discovery import rag_discovery
from app.core.exceptions import ToolPlatformError
from app.core.log_context import (
    STATUS_INTERNAL_ERROR,
    STATUS_SUCCESS,
    STATUS_TOOL_NOT_FOUND,
    STATUS_UPSTREAM_ERROR,
    STATUS_VALIDATION_ERROR,
    RequestLogContext,
    current_log_context,
    request_log_ctx,
)
from app.core.logging_config import configure_logging, get_app_logger
from app.core.nacos import NacosRegistrar
from app.core.openapi import OPENAPI_TAGS, SWAGGER_UI_PARAMETERS
from app.core.registry import tool_registry
from app.core.responses import echo_ctx, error, extract_echo_ids, trace_id_ctx

settings = get_settings()
configure_logging(settings)
logger = get_app_logger(__name__)

nacos_registrar = NacosRegistrar(settings)

# 业务错误码 -> 完成日志 status（设计 §8.2）
STATUS_BY_BUSINESS_CODE = {
    40000: STATUS_VALIDATION_ERROR,
    40400: STATUS_TOOL_NOT_FOUND,
    50200: STATUS_UPSTREAM_ERROR,
    50300: STATUS_UPSTREAM_ERROR,
    50400: STATUS_UPSTREAM_ERROR,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # uvicorn CLI 启动时会覆盖 logging 配置，启动阶段再应用一次确保 app.* 日志可见
    configure_logging(settings)
    # ---- 启动：绑定契约 + 注册 Nacos ----
    tool_registry.load_contracts(settings.skills_dir)
    logger.info(
        "工具注册完成，共 %d 个: %s",
        len(tool_registry.list_tools()),
        [t["tool_name"] for t in tool_registry.list_tools()],
        extra={"event": "tool.contracts.loaded"},
    )
    # naming service 首次创建成功（含保活补偿重建）时补挂服务发现
    async def _on_naming_ready(naming_service) -> None:
        rag_discovery.attach(naming_service)
        await rag_discovery.start()

    nacos_registrar.set_on_naming_ready(_on_naming_ready)
    await nacos_registrar.register()
    # ---- 启动 RAG 服务发现（复用注册时的 naming service） ----
    rag_discovery.attach(nacos_registrar.naming_service)
    await rag_discovery.start()
    logger.info("服务启动完成", extra={"event": "service.started"})
    yield
    # ---- 关闭：停止发现 + 注销 Nacos ----
    logger.info("服务开始关闭", extra={"event": "service.stopping"})
    await rag_discovery.stop()
    await nacos_registrar.deregister()


app = FastAPI(
    title="Roxie Tool 中台",
    description=(
        "面向 Agent 的工具注册、发现与统一调用服务（roxie-router-service）。\n\n"
        "## Agent 接入流程\n"
        "1. 通过 Nacos 按 `service-name=roxie-router-service` 发现本中台地址\n"
        "2. `GET /api/v1/tools` — 工具发现（摘要列表）\n"
        "3. `GET /api/v1/tools/{tool_name}` — 获取完整契约（input/output schema）\n"
        "4. `POST /api/v1/tools/{tool_name}/invoke` — 统一调用\n\n"
        "## 响应格式\n"
        "所有接口统一返回 `{code, message, data, trace_id}` 信封；"
        "工具 invoke 响应额外固定包含 `echo`。可通过请求头 `X-Trace-Id` 透传链路追踪 ID；"
        "请求体顶层 `id` / `*_id` 标量字段会进入 echo，但不会作为工具参数转发。\n\n"
        "## 已实现工具\n"
        "| tool_name | 说明 |\n"
        "|---|---|\n"
        "| dtc_context_service | 单个 DTC 解析为背景上下文 |\n"
        "| dtc_grouping_service | 多 DTC 聚合分组 |\n"
        "| cause_ranking_service | 候选原因拉取与排序 |\n"
        "| diagnostic_planning_service | 诊断检查项拉取与排序 |\n"
        "| maintenance_light_reset_service | 保养归零 SOP / 执行 |\n"
        "| repair_planning_service | 维修方案输出 |\n"
        "| dtc_cause_cards_service | DTC 原因处置卡片聚合 |"
    ),
    version=settings.app_version,
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_parameters=SWAGGER_UI_PARAMETERS,
)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """根路径重定向到 Swagger UI。"""
    return RedirectResponse(url="/docs")


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    """管理请求级 trace_id、invoke echo 与日志上下文，并输出一条请求完成摘要。"""
    started = time.perf_counter()
    trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
    trace_token = trace_id_ctx.set(trace_id)
    echo_token = echo_ctx.set({})
    log_token = request_log_ctx.set(RequestLogContext())
    is_invoke = _is_invoke_request(request)
    try:
        if is_invoke:
            try:
                payload = await request.json()
            except (UnicodeDecodeError, ValueError):
                payload = None
            request_echo = extract_echo_ids(payload)
            request.state.invoke_echo = request_echo
            echo_ctx.set(request_echo)
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        _log_request_completed(
            request, started, is_invoke,
            response.status_code, response.headers.get("content-length"),
        )
        return response
    except Exception as exc:  # noqa: BLE001 - 未知异常的唯一堆栈出口
        # 必须在 finally 清理 ContextVar 之前记录：Starlette 的 ServerErrorMiddleware
        # 位于本 middleware 之外，若留到全局异常处理器再记，堆栈将丢失 trace_id
        _log_unhandled_error(request, exc)
        _update_log_context(STATUS_INTERNAL_ERROR, exc, business_code=50000)
        _log_request_completed(request, started, is_invoke, 500, None)
        raise
    finally:
        request_log_ctx.reset(log_token)
        echo_ctx.reset(echo_token)
        trace_id_ctx.reset(trace_token)


def _is_invoke_request(request: Request) -> bool:
    return request.method == "POST" and request.url.path.endswith("/invoke")


def _content_length(raw: str | None) -> int | None:
    """从 Content-Length 头取字节数，取不到时省略该字段（不重复序列化正文）。"""
    try:
        return int(raw) if raw is not None else None
    except ValueError:
        return None


def _completion_status(status: str, http_status: int) -> str:
    """异常处理器未设置 status 时（如路由 404），按 HTTP 状态兜底。"""
    if status != STATUS_SUCCESS or http_status < 400:
        return status
    if http_status == 404:
        return STATUS_TOOL_NOT_FOUND
    if http_status < 500:
        return STATUS_VALIDATION_ERROR
    return STATUS_INTERNAL_ERROR


def _completion_level(http_status: int) -> int:
    if http_status >= 500:
        return logging.ERROR
    if http_status >= 400:
        return logging.WARNING
    return logging.INFO


def _log_request_completed(
    request: Request,
    started: float,
    is_invoke: bool,
    http_status: int,
    response_length: str | None,
) -> None:
    """输出请求完成摘要：只含白名单字段，不含请求体、返回结果与 Header。"""
    log_ctx = current_log_context() or RequestLogContext()
    business_code = log_ctx.business_code
    if business_code is None and http_status < 400:
        business_code = 0
    fields = {
        "event": "tool.invoke.completed" if is_invoke else "http.request.completed",
        "tool_name": log_ctx.tool_name,
        "status": _completion_status(log_ctx.status, http_status),
        "http_method": request.method,
        "http_path": request.url.path,
        "http_status": http_status,
        "business_code": business_code,
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        "request_bytes": _content_length(request.headers.get("content-length")),
        "response_bytes": _content_length(response_length),
        "dtc_count": log_ctx.dtc_count,
        "error_type": log_ctx.error_type,
    }
    logger.log(
        _completion_level(http_status),
        "请求完成",
        extra={key: value for key, value in fields.items() if value is not None},
    )


def _log_unhandled_error(request: Request, exc: Exception) -> None:
    """未知异常的唯一堆栈日志；Formatter 只输出异常类型与帧位置，不含异常正文。"""
    logger.error(
        "未处理异常",
        exc_info=exc,
        extra={
            "event": "application.unhandled_error",
            "http_method": request.method,
            "http_path": request.url.path,
            "error_type": type(exc).__name__,
        },
    )


def _update_log_context(status: str, exc: Exception, business_code: int | None = None) -> None:
    """异常处理器更新请求日志上下文，只写状态、业务码与异常类型。"""
    log_ctx = current_log_context()
    if log_ctx is None:
        return
    log_ctx.status = status
    log_ctx.error_type = type(exc).__name__
    if business_code is not None:
        log_ctx.business_code = business_code


def _error_content(request: Request, code: int, message: str) -> dict:
    content = error(code, message).model_dump()
    if _is_invoke_request(request):
        request_echo = getattr(request.state, "invoke_echo", echo_ctx.get())
        content["echo"] = dict(request_echo)
    return content


@app.exception_handler(ToolPlatformError)
async def tool_platform_error_handler(request: Request, exc: ToolPlatformError) -> JSONResponse:
    status_code = {
        40000: 400,
        40400: 404,
        50200: 502,
        50300: 503,
        50400: 504,
    }.get(exc.code, 500)
    _update_log_context(
        STATUS_BY_BUSINESS_CODE.get(exc.code, STATUS_INTERNAL_ERROR), exc, business_code=exc.code
    )
    return JSONResponse(
        status_code=status_code,
        content=_error_content(request, exc.code, exc.message),
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    if not _is_invoke_request(request):
        _update_log_context(STATUS_VALIDATION_ERROR, exc)
        return await request_validation_exception_handler(request, exc)
    _update_log_context(STATUS_VALIDATION_ERROR, exc, business_code=40000)
    return JSONResponse(
        status_code=400,
        content=_error_content(request, 40000, f"请求入参校验失败: {exc}"),
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """只负责响应；堆栈与完成摘要已由 middleware 在请求上下文内各记录一次。"""
    return JSONResponse(
        status_code=500,
        content=_error_content(request, 50000, f"服务内部错误: {exc}"),
    )


app.include_router(api_router)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        # 日志已由 configure_logging() 统一配置，禁止 uvicorn 覆盖
        log_config=None,
    )
