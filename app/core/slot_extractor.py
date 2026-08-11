"""按工具 input_schema 的 ``x-extract`` 声明提取规范入参。"""
from __future__ import annotations

from typing import Any


def _values_at_path(source: Any, path: str) -> list[Any]:
    """读取点分路径；字段名后的 ``[]`` 表示展开该数组。"""
    nodes = [source]
    for raw_segment in path.split("."):
        expand = raw_segment.endswith("[]")
        key = raw_segment[:-2] if expand else raw_segment
        next_nodes: list[Any] = []
        for node in nodes:
            if not isinstance(node, dict) or key not in node:
                continue
            value = node[key]
            if expand:
                if isinstance(value, list):
                    next_nodes.extend(value)
            else:
                next_nodes.append(value)
        nodes = next_nodes
        if not nodes:
            break
    return nodes


def _flatten(values: list[Any]) -> list[Any]:
    flattened: list[Any] = []
    for value in values:
        if isinstance(value, list):
            flattened.extend(_flatten(value))
        else:
            flattened.append(value)
    return flattened


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _normalize_scalar(field_name: str, value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
    if field_name == "year" and isinstance(value, str) and value.isdecimal():
        return int(value)
    return value


def _normalize_array(field_name: str, values: list[Any]) -> list[Any]:
    normalized: list[Any] = []
    seen: set[Any] = set()
    for value in _flatten(values):
        if _is_empty(value):
            continue
        value = _normalize_scalar(field_name, value)
        if field_name == "dtc_codes" and isinstance(value, str):
            value = value.upper()
        marker = value if isinstance(value, (str, int, float, bool, type(None))) else repr(value)
        if marker in seen:
            continue
        seen.add(marker)
        normalized.append(value)
    return normalized


def extract_slots(arguments: dict[str, Any], input_schema: dict[str, Any]) -> dict[str, Any]:
    """把 Agent 大请求投影成当前工具声明的规范字段。"""
    mappings = input_schema.get("x-extract")
    properties = input_schema.get("properties")
    if not isinstance(mappings, dict):
        if not isinstance(properties, dict):
            return arguments
        return {
            field_name: arguments[field_name]
            for field_name in properties
            if field_name in arguments
        }

    properties = properties if isinstance(properties, dict) else {}
    extracted: dict[str, Any] = {}
    for field_name, configured_paths in mappings.items():
        paths = configured_paths if isinstance(configured_paths, list) else [configured_paths]
        field_schema = properties.get(field_name, {})
        is_array = field_schema.get("type") == "array"
        for path in paths:
            if not isinstance(path, str):
                continue
            values = _values_at_path(arguments, path)
            if is_array:
                normalized = _normalize_array(field_name, values)
                if normalized:
                    extracted[field_name] = normalized
                    break
                continue
            value = next((item for item in values if not _is_empty(item)), None)
            if value is not None:
                extracted[field_name] = _normalize_scalar(field_name, value)
                break
    return extracted
