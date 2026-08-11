"""Roxie Tool 中台入口。

启动流程：
1. 导入 app.tools 触发各工具 @register_tool 自注册（注册 handler）
2. 扫描 myskills/*/tool-schema.json 加载契约并绑定
3. 注册到 Nacos 并启动心跳
4. 关闭时从 Nacos 注销
"""
import logging
import uuid
from contextlib import asynccontextmanager
from logging.config import dictConfig

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

import app.tools  # noqa: F401 - 导入即完成工具自注册
from app.api.v1.router import api_router
from app.config import get_settings
from app.core.discovery import rag_discovery
from app.core.exceptions import ToolPlatformError
from app.core.logging_config import LOGGING_CONFIG, get_app_logger
from app.core.nacos import NacosRegistrar
from app.core.openapi import OPENAPI_TAGS, SWAGGER_UI_PARAMETERS
from app.core.registry import tool_registry
from app.core.responses import error, trace_id_ctx

dictConfig(LOGGING_CONFIG)
logger = get_app_logger(__name__)

settings = get_settings()
nacos_registrar = NacosRegistrar(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # uvicorn CLI 启动时会覆盖 logging 配置，启动阶段再应用一次确保 app.* 日志可见
    dictConfig(LOGGING_CONFIG)
    # ---- 启动：绑定契约 + 注册 Nacos ----
    tool_registry.load_contracts(settings.skills_dir)
    logger.info("工具注册完成，共 %d 个: %s", len(tool_registry.list_tools()),
                [t["tool_name"] for t in tool_registry.list_tools()])
    # naming service 首次创建成功（含保活补偿重建）时补挂服务发现
    async def _on_naming_ready(naming_service) -> None:
        rag_discovery.attach(naming_service)
        await rag_discovery.start()

    nacos_registrar.set_on_naming_ready(_on_naming_ready)
    await nacos_registrar.register()
    # ---- 启动 RAG 服务发现（复用注册时的 naming service） ----
    rag_discovery.attach(nacos_registrar.naming_service)
    await rag_discovery.start()
    yield
    # ---- 关闭：停止发现 + 注销 Nacos ----
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
        "可通过请求头 `X-Trace-Id` 透传链路追踪 ID。\n\n"
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
    """透传或生成 trace_id，写入响应信封与响应头。"""
    trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
    token = trace_id_ctx.set(trace_id)
    if request.method == "POST" and request.url.path.endswith("/invoke"):
        logger.info("收到工具调用请求: %s", request.url.path)
    try:
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response
    finally:
        trace_id_ctx.reset(token)


@app.exception_handler(ToolPlatformError)
async def tool_platform_error_handler(request: Request, exc: ToolPlatformError) -> JSONResponse:
    status_code = {
        40000: 400,
        40400: 404,
        50200: 502,
        50300: 503,
        50400: 504,
    }.get(exc.code, 500)
    return JSONResponse(status_code=status_code, content=error(exc.code, exc.message).model_dump())


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理异常: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content=error(50000, f"服务内部错误: {exc}").model_dump())


app.include_router(api_router)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_config=LOGGING_CONFIG,
    )
