"""基于 tool-schema.json 契约的 JSON Schema 校验。"""
from typing import Any

import jsonschema


def validate_against_schema(instance: dict, schema: dict) -> str | None:
    """校验数据是否满足 JSON Schema。

    返回 None 表示通过；否则返回可读的错误描述。
    """
    validator_cls = jsonschema.validators.validator_for(schema)
    validator = validator_cls(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    if not errors:
        return None
    messages = []
    for err in errors[:5]:
        path = ".".join(str(p) for p in err.absolute_path) or "(root)"
        messages.append(f"{path}: {err.message}")
    return "; ".join(messages)


def _resolve_ref(schema: Any, root: dict) -> Any:
    """解析本地 $ref（#/definitions/... 形式），非 $ref 原样返回。"""
    if isinstance(schema, dict) and "$ref" in schema:
        ref = schema["$ref"]
        if ref.startswith("#/"):
            node: Any = root
            for part in ref[2:].split("/"):
                if not isinstance(node, dict) or part not in node:
                    return schema
                node = node[part]
            return node
    return schema


def _allows_null(schema: Any, root: dict | None = None) -> bool:
    """判断 schema 是否显式允许 null（type 含 null 或 oneOf/anyOf 含 null 分支）。"""
    if root is not None:
        schema = _resolve_ref(schema, root)
    if not isinstance(schema, dict):
        return False
    t = schema.get("type")
    if t == "null" or (isinstance(t, list) and "null" in t):
        return True
    return any(
        _allows_null(branch, root)
        for key in ("oneOf", "anyOf")
        for branch in (schema.get(key) or [])
    )


def strip_invalid_nulls(data: Any, schema: Any, _root: dict | None = None) -> Any:
    """递归移除 schema 不允许为 null 的 None 值（视为字段缺省）。

    远程服务对未填充的可选字段返回显式 null，
    而契约中这些字段类型为 string/array 等（不允许 null）。
    规范化后 None 字段被移除，显式允许 null 的字段（如 repair_plan）保留。
    支持解析契约内的本地 $ref（#/definitions/...）。
    """
    root = _root if _root is not None else (schema if isinstance(schema, dict) else {})
    schema = _resolve_ref(schema, root)

    if isinstance(data, dict):
        props = schema.get("properties", {}) if isinstance(schema, dict) else {}
        out = {}
        for key, value in data.items():
            prop_schema = props.get(key, {})
            if value is None:
                if _allows_null(prop_schema, root):
                    out[key] = None
                # 不允许 null 则丢弃该字段（等价于未返回）
            else:
                out[key] = strip_invalid_nulls(value, prop_schema, root)
        return out
    if isinstance(data, list):
        item_schema = schema.get("items", {}) if isinstance(schema, dict) else {}
        items = [strip_invalid_nulls(item, item_schema, root) for item in data]
        if not _allows_null(item_schema, root):
            items = [item for item in items if item is not None]
        return items
    return data
