"""cause_ranking_service：候选原因检索/排序（远程代理）。

业务实现位于 roxie-rag-service（POST /api/v1/tool-services/cause-ranking），
本 handler 经 Nacos 服务发现转发请求并透传结果。
"""
from typing import Any

from app.config import get_settings
from app.core.registry import register_tool
from app.services.rag_client import rag_client


@register_tool("cause_ranking_service")
def cause_ranking_service(args: dict[str, Any]) -> dict[str, Any]:
    return rag_client.invoke(
        "cause_ranking_service",
        "cause-ranking",
        args,
        timeout=get_settings().cause_ranking_timeout,
    )
