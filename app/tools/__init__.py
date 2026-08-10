"""业务工具包：导入即触发各工具的 @register_tool 自注册。"""
from app.tools import (  # noqa: F401
    cause_ranking,
    diagnose,
    diagnostic_planning,
    dtc_cause_cards,
    dtc_context,
    dtc_grouping,
    maintenance_light_reset,
    repair_planning,
)
