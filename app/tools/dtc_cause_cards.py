"""dtc_cause_cards_service：DTC 原因处置卡片聚合（远程代理）。

业务实现位于 roxie-rag-service（POST /api/v1/dtc-cause-cards），
本 handler 经 Nacos 服务发现转发请求并透传结果。
该接口含 LLM 补全（检查判据 / 操作提示 / 维修后验证），
耗时长于普通工具，故使用独立的 diagnose_timeout 超时配置。
"""
from typing import Any

from app.config import get_settings
from app.core.registry import register_tool
from app.services.rag_client import rag_client


@register_tool("dtc_cause_cards_service")
def dtc_cause_cards_service(args: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    return rag_client.invoke(
        "dtc_cause_cards_service",
        "dtc-cause-cards",
        args,
        service_name=settings.rag_service_name,
        base_path=settings.diagnose_base_path,
        timeout=settings.diagnose_timeout,
    )
