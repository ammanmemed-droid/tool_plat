"""maintenance_light_reset_service：保养归零 SOP 指引（guide）与授权执行（execute）。

规则（来自 maintenance-light-reset-skill/SKILL.md）：
- 资料匹配优先级：品牌+车型+年款 -> 相近年款 -> 通用路径
- 未命中精确案例必须明确提示，不得伪装精确步骤
- execute 模式必须满足：设备连接 + 设备支持 + 用户确认，缺一不可执行
"""
from app.core.registry import register_tool
from app.tools.base import norm
from app.tools.knowledge import GENERIC_RESET_SOP, MAINTENANCE_SOP_DB

CONFIRMATION_PROMPT = (
    "即将对当前车辆执行保养灯归零。执行后，仪表保养周期可能被重置。"
    "请确认车辆已完成实际保养，是否继续？"
)


def _match_sop(brand: str, model: str, year: str) -> tuple[dict | None, str | None]:
    """按优先级匹配 SOP，返回 (资料, 不确定性说明)。"""
    b, m, y = norm(brand), norm(model), norm(year)
    for sop in MAINTENANCE_SOP_DB:
        if norm(sop["brand"]) != b:
            continue
        sop_model = norm(sop["model"])
        model_hit = sop_model == m or (sop_model and sop_model in m) or (m and m in sop_model)
        if not model_hit:
            continue
        if y and y in [norm(x) for x in sop["years"]]:
            return sop, None
        # 品牌+车型命中但年款不同 -> 相似案例
        similar = dict(sop)
        similar["source_type"] = "similar_case"
        similar["source_confidence"] = "medium"
        return similar, (
            f"未匹配到 {brand} {model} {year} 的精确案例，以下为同车型相近年款案例"
            f"（适用年款: {', '.join(sop['years'])}），具体操作以实际设备界面为准。"
        )
    return None, None


def _missing_vehicle_fields(brand: str, model: str, year: str) -> list[str]:
    missing: list[str] = []
    if not brand.strip():
        missing.append("brand")
    if not model.strip():
        missing.append("model")
    if not year.strip():
        missing.append("year")
    return missing


@register_tool("maintenance_light_reset_service")
def maintenance_light_reset_service(args: dict) -> dict:
    brand = args.get("brand", "")
    model = args.get("model", "")
    year = args.get("year", "")
    action_mode = args.get("action_mode", "guide")

    missing_vehicle = _missing_vehicle_fields(brand, model, year)
    if missing_vehicle:
        return {
            "action_mode": action_mode,
            "uncertainty_note": "缺少品牌、车型或年款等关键信息，无法匹配保养归零资料或执行设备操作。",
            "missing_required_info": missing_vehicle,
        }

    # ---------------- guide 模式 ----------------
    if action_mode == "guide":
        sop, note = _match_sop(brand, model, year)
        if sop is None:
            guide = {
                "applicable_vehicle": {"brand": brand, "model": model, "year": year},
                "source_type": GENERIC_RESET_SOP["source_type"],
                "source_confidence": GENERIC_RESET_SOP["source_confidence"],
                "steps": GENERIC_RESET_SOP["steps"],
                "uncertainty_note": (
                    f"未匹配到 {brand} {model} {year} 的精确案例，以下为通用保养归零路径，"
                    "具体操作以实际设备界面为准。"
                ),
            }
            return {"action_mode": "guide", "maintenance_reset_guide": guide}

        guide = {
            "applicable_vehicle": {"brand": brand, "model": model, "year": year},
            "source_type": sop["source_type"],
            "source_confidence": sop["source_confidence"],
            "steps": sop["steps"],
        }
        if note:
            guide["uncertainty_note"] = note
        return {"action_mode": "guide", "maintenance_reset_guide": guide}

    # ---------------- execute 模式 ----------------
    missing: list[str] = []
    connection = args.get("device_connection_status")
    capability = args.get("device_capability") or {}
    user_confirmation = args.get("user_confirmation")

    if not connection:
        missing.append("device_connection_status")
    if not capability:
        missing.append("device_capability")
    if missing:
        return {
            "action_mode": "execute",
            "execution_result": {
                "execution_status": "failed",
                "uncertainty_note": "execute 模式缺少必要条件，不得执行。",
            },
            "missing_required_info": missing,
        }

    # 设备连接检查
    if connection != "connected":
        return {
            "action_mode": "execute",
            "execution_result": {
                "execution_status": "failed",
                "device_message": f"设备当前连接状态为 {connection}，请连接诊断设备后重试。",
                "uncertainty_note": "设备未连接，无法执行保养归零。",
            },
        }

    # 设备能力检查
    if not capability.get("supports_maintenance_reset", False) or not capability.get("supported_vehicle", False):
        return {
            "action_mode": "execute",
            "execution_result": {
                "execution_status": "not_supported",
                "device_message": capability.get("capability_note", "当前设备不支持该车型保养归零。"),
                "uncertainty_note": "当前设备不支持对该车型执行保养归零，可改用 guide 模式输出 SOP 由用户自行操作。",
            },
        }

    # 用户取消
    if user_confirmation is False:
        return {
            "action_mode": "execute",
            "execution_result": {
                "execution_status": "cancelled",
                "executed_action": "保养灯归零",
                "device_message": "用户已取消保养灯归零操作。",
            },
        }

    # 用户确认检查
    if user_confirmation is not True:
        return {
            "action_mode": "execute",
            "execution_result": {
                "execution_status": "awaiting_confirmation",
                "executed_action": "保养灯归零",
                "confirmation_prompt": CONFIRMATION_PROMPT,
            },
        }

    # 执行（设备适配层集成点：此处模拟设备执行成功）
    return {
        "action_mode": "execute",
        "execution_result": {
            "execution_status": "success",
            "executed_action": "保养灯归零",
            "device_message": f"已对 {brand} {model} {year} 执行保养灯归零，设备返回成功。请启动车辆确认仪表保养提示已清除。",
        },
    }
