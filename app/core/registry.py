"""工具注册中心：负责工具的注册、契约绑定、发现与调用。

设计要点：
1. 工具业务实现通过 @register_tool 装饰器自注册（注册 handler）。
2. 注册中心启动时扫描 myskills/*/tool-schema.json 加载契约
   （tool_name / description / input_schema / output_schema），
   并与 handler 按 tool_name 绑定。
3. Agent 通过发现接口拿到工具清单与契约，通过统一 invoke 接口调用，
   中台在调用前后分别按 input_schema / output_schema 做校验。
"""
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.exceptions import (
    ToolExecutionError,
    ToolInputValidationError,
    ToolNotFoundError,
    ToolOutputValidationError,
    ToolPlatformError,
)
from app.core.validation import strip_invalid_nulls, validate_against_schema

logger = logging.getLogger(__name__)

ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class ToolDefinition:
    """一个已注册工具 = 业务 handler + 契约 schema。"""

    tool_name: str
    description: str
    handler: ToolHandler
    tool_kind: str = "global_tool_service"
    skill_name: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        """发现接口用的摘要信息。"""
        return {
            "tool_name": self.tool_name,
            "tool_kind": self.tool_kind,
            "description": self.description,
            "skill_name": self.skill_name,
        }

    def detail(self) -> dict[str, Any]:
        """发现接口用的完整契约信息（供 Agent 组织入参）。"""
        return {
            **self.summary(),
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }


class ToolRegistry:
    """工具注册中心单例。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    # ---------- 注册 ----------

    def register(self, tool_name: str, handler: ToolHandler) -> None:
        """业务模块自注册入口（装饰器调用）。"""
        if tool_name in self._tools:
            logger.warning("工具重复注册，将被覆盖: %s", tool_name)
        self._tools[tool_name] = ToolDefinition(tool_name=tool_name, description="", handler=handler)
        logger.info("工具 handler 已注册: %s", tool_name)

    def load_contracts(self, skills_dir: Path) -> None:
        """扫描 skills 目录下的 tool-schema.json，绑定契约到已注册工具。"""
        if not skills_dir.exists():
            raise ToolPlatformError(f"技能契约目录不存在: {skills_dir}")

        schema_files = sorted(skills_dir.glob("*/tool-schema.json"))
        logger.info("扫描到 %d 个 tool-schema.json: %s", len(schema_files), skills_dir)

        bound: set[str] = set()
        for schema_file in schema_files:
            contract = json.loads(schema_file.read_text(encoding="utf-8"))
            tool_name = contract.get("tool_name")
            if not tool_name:
                logger.warning("契约缺少 tool_name，已跳过: %s", schema_file)
                continue
            tool = self._tools.get(tool_name)
            if tool is None:
                logger.warning("契约 %s 无对应已注册 handler，已跳过", tool_name)
                continue
            tool.description = contract.get("description", "")
            tool.tool_kind = contract.get("tool_kind", "global_tool_service")
            tool.skill_name = schema_file.parent.name
            tool.input_schema = contract.get("input_schema", {})
            tool.output_schema = contract.get("output_schema", {})
            bound.add(tool_name)
            logger.info("契约已绑定: %s <- %s", tool_name, schema_file)

        unbound = set(self._tools) - bound
        if unbound:
            logger.warning("以下工具缺少契约文件: %s", sorted(unbound))

    # ---------- 发现 ----------

    def list_tools(self) -> list[dict[str, Any]]:
        return [tool.summary() for tool in self._tools.values()]

    def get_tool(self, tool_name: str) -> ToolDefinition:
        tool = self._tools.get(tool_name)
        if tool is None:
            raise ToolNotFoundError(tool_name)
        return tool

    # ---------- 调用 ----------

    def invoke(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """统一调用入口：槽位提取 -> 入参归一化 -> 校验 -> 执行 -> 出参校验。"""
        from app.core.slot_extractor import extract_slots
        from app.tools.argument_normalizers import normalize_arguments

        tool = self.get_tool(tool_name)
        arguments = extract_slots(arguments, tool.input_schema)
        arguments = normalize_arguments(tool_name, arguments)

        if tool.input_schema:
            err = validate_against_schema(arguments, tool.input_schema)
            if err:
                raise ToolInputValidationError(tool_name, err)

        try:
            result = tool.handler(arguments)
        except ToolPlatformError:
            raise
        except Exception as exc:  # noqa: BLE001 - 统一兜底为执行异常
            logger.exception("工具执行异常: %s", tool_name)
            raise ToolExecutionError(tool_name, str(exc)) from exc

        if tool.output_schema:
            # 规范化：契约不允许 null 的 None 字段视为缺省（兼容远端 null 占位响应）
            result = strip_invalid_nulls(result, tool.output_schema)
            err = validate_against_schema(result, tool.output_schema)
            if err:
                raise ToolOutputValidationError(tool_name, err)

        return result


# 全局单例
tool_registry = ToolRegistry()


def register_tool(tool_name: str) -> Callable[[ToolHandler], ToolHandler]:
    """业务工具注册装饰器。"""

    def decorator(func: ToolHandler) -> ToolHandler:
        tool_registry.register(tool_name, func)
        return func

    return decorator
