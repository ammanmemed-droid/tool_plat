"""dtc_grouping_service：多 DTC 关联分组（远程代理）。

业务实现位于 roxie-rag-service（POST /api/v1/tool-services/dtc-grouping），
本 handler 经 Nacos 服务发现转发请求并透传结果。
"""
from typing import Any

from app.core.registry import register_tool
from app.services.rag_client import rag_client


@register_tool("dtc_grouping_service")
def dtc_grouping_service(args: dict[str, Any]) -> dict[str, Any]:
    return rag_client.invoke("dtc_grouping_service", "dtc-grouping", args)
