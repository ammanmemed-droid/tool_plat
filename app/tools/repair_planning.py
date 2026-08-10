"""repair_planning_service：维修计划生成（远程代理）。

业务实现位于 roxie-rag-service（POST /api/v1/tool-services/repair-planning），
本 handler 经 Nacos 服务发现转发请求并透传结果。
"""
from typing import Any

from app.core.registry import register_tool
from app.services.rag_client import rag_client


@register_tool("repair_planning_service")
def repair_planning_service(args: dict[str, Any]) -> dict[str, Any]:
    return rag_client.invoke("repair_planning_service", "repair-planning", args)
