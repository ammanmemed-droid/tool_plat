"""diagnostic_planning_service：诊断检查项/计划（远程代理）。

业务实现位于 roxie-rag-service（POST /api/v1/tool-services/diagnostic-planning），
本 handler 经 Nacos 服务发现转发请求并透传结果。
"""
from typing import Any

from app.core.registry import register_tool
from app.services.rag_client import rag_client


@register_tool("diagnostic_planning_service")
def diagnostic_planning_service(args: dict[str, Any]) -> dict[str, Any]:
    return rag_client.invoke("diagnostic_planning_service", "diagnostic-planning", args)
