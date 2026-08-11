"""工具入参归一化：在 JSON Schema 校验前将 Agent 常见写法转为契约字段。"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

NORMALIZERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def register_normalizer(tool_name: str) -> Callable[[Callable], Callable]:
    """注册某工具的入参归一化函数。"""

    def decorator(func: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable:
        NORMALIZERS[tool_name] = func
        return func

    return decorator


def normalize_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    normalizer = NORMALIZERS.get(tool_name)
    if normalizer is None:
        return arguments
    return normalizer(dict(arguments))
