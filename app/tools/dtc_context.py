"""dtc_context_service：DTC 背景上下文解析（远程代理）。

业务实现位于 roxie-rag-service（POST /api/v1/tool-services/dtc-context），
本 handler 经 Nacos 服务发现转发请求并透传结果。
"""
from typing import Any

from app.core.registry import register_tool
from app.services.rag_client import rag_client


@register_tool("dtc_context_service")
def dtc_context_service(args: dict[str, Any]) -> dict[str, Any]:
    return rag_client.invoke("dtc_context_service", "dtc-context", args)
