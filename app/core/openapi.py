"""OpenAPI / Swagger 文档配置。"""

OPENAPI_TAGS = [
    {
        "name": "health",
        "description": "健康检查，供 Nacos / 负载均衡探活。",
    },
    {
        "name": "tools",
        "description": (
            "Agent 工具发现与统一调用。\n\n"
            "**接入流程：**\n"
            "1. `GET /api/v1/tools` — 列出全部工具摘要\n"
            "2. `GET /api/v1/tools/{tool_name}` — 获取 input/output schema\n"
            "3. `POST /api/v1/tools/{tool_name}/invoke` — 传入 arguments 执行工具"
        ),
    },
]

COMMON_RESPONSES: dict = {
    400: {
        "description": "入参校验失败（不满足 tool input_schema 或请求体格式错误）",
        "content": {
            "application/json": {
                "example": {
                    "code": 40000,
                    "message": "工具 dtc_context_service 入参校验失败: dtc_code: 'dtc_code' is a required property",
                    "data": None,
                    "trace_id": "a1b2c3d4e5f6",
                },
            },
        },
    },
    404: {
        "description": "工具不存在",
        "content": {
            "application/json": {
                "example": {
                    "code": 40400,
                    "message": "工具不存在: not_exist_tool",
                    "data": None,
                    "trace_id": "a1b2c3d4e5f6",
                },
            },
        },
    },
    500: {
        "description": "服务内部错误或工具执行/出参校验失败",
        "content": {
            "application/json": {
                "example": {
                    "code": 50000,
                    "message": "服务内部错误: ...",
                    "data": None,
                    "trace_id": "a1b2c3d4e5f6",
                },
            },
        },
    },
}

SWAGGER_UI_PARAMETERS = {
    "docExpansion": "list",
    "defaultModelsExpandDepth": 2,
    "displayRequestDuration": True,
    "filter": True,
    "tryItOutEnabled": True,
}
