"""dtc_grouping_service：多 DTC 关联分组（远程代理）。

业务实现位于 roxie-rag-service（POST /api/v1/tool-services/dtc-grouping），
本 handler 经 Nacos 服务发现转发请求并透传结果。
"""
from typing import Any

from app.core.registry import register_tool
from app.services.rag_client import rag_client
from app.tools.argument_normalizers import _flatten_vehicle_info, register_normalizer


def _build_dtc_entries(
    dtc_list: list[str],
    brand: str,
    vehicle_info: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """缺少 dtc_entries 时，逐码调用 dtc_context_service 补全 system / related_parts。"""
    entries: list[dict[str, Any]] = []
    context_base: dict[str, Any] = {"brand": brand}
    if vehicle_info:
        context_base["vehicle_info"] = vehicle_info

    for code in dtc_list:
        normalized = str(code or "").strip()
        if not normalized:
            continue
        result = rag_client.invoke(
            "dtc_context_service",
            "dtc-context",
            {**context_base, "dtc_code": normalized},
        )
        ctx = result.get("dtc_context") or {}
        system = str(ctx.get("system") or ctx.get("subsystem") or "").strip()
        parts = ctx.get("related_parts") or []
        if not isinstance(parts, list):
            parts = []
        entries.append(
            {
                "dtc_code": normalized.upper(),
                "system": system or "未知系统",
                "related_parts": [p for p in parts if isinstance(p, str) and p.strip()],
            }
        )
    return entries


@register_normalizer("dtc_grouping_service")
def normalize_dtc_grouping_arguments(args: dict[str, Any]) -> dict[str, Any]:
    """兼容 dtc_codes/dtcs 别名，并自动补全 dtc_entries。"""
    payload = _flatten_vehicle_info(dict(args))

    if "dtc_list" not in payload:
        if "dtc_codes" in payload:
            payload["dtc_list"] = payload.pop("dtc_codes")
        elif "dtcs" in payload:
            payload["dtc_list"] = payload.pop("dtcs")

    dtc_list = payload.get("dtc_list")
    brand = payload.get("brand")
    if payload.get("dtc_entries") is None and isinstance(dtc_list, list) and brand:
        payload["dtc_entries"] = _build_dtc_entries(dtc_list, str(brand), payload.get("vehicle_info"))

    return payload


@register_tool("dtc_grouping_service")
def dtc_grouping_service(args: dict[str, Any]) -> dict[str, Any]:
    return rag_client.invoke("dtc_grouping_service", "dtc-grouping", args)
