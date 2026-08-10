"""一次性脚本：从 roxie-rag-service 最新 OpenAPI 提取 /api/v1/diagnoses 契约并与本地对比。

- 提取 DiagnoseRequest / DiagnoseResponse，$ref 重写为本地 #/$defs 形式
- 与 myskills/diagnose-skill/tool-schema.json 做字段级结构对比
- 结果：_diagnose_remote.json（远端契约）、_diagnose_diff.txt（差异报告）
"""
import json
from typing import Any

openapi = json.load(open("_openapi_rag-service.json", encoding="utf-8"))
local = json.load(open("myskills/diagnose-skill/tool-schema.json", encoding="utf-8"))

path_item = openapi["paths"]["/api/v1/diagnoses"]["post"]
req_ref = path_item["requestBody"]["content"]["application/json"]["schema"]
resp_ref = path_item["responses"]["200"]["content"]["application/json"]["schema"]
components = openapi["components"]["schemas"]


def collect(schema: Any, defs: dict) -> Any:
    """递归重写 $ref 并收集 referenced components 到 defs。"""
    if isinstance(schema, dict):
        out = {}
        for k, v in schema.items():
            if k == "$ref" and isinstance(v, str) and v.startswith("#/components/schemas/"):
                name = v.rsplit("/", 1)[-1]
                if name not in defs:
                    defs[name] = None  # 占位防循环
                    defs[name] = collect(components[name], defs)
                out[k] = f"#/$defs/{name}"
            else:
                out[k] = collect(v, defs)
        return out
    if isinstance(schema, list):
        return [collect(i, defs) for i in schema]
    return schema


def build(root_ref: dict) -> dict:
    defs: dict = {}
    schema = collect(root_ref, defs)
    if schema.get("$ref", "").startswith("#/$defs/"):
        name = schema["$ref"].rsplit("/", 1)[-1]
        schema = dict(defs[name])
        defs.pop(name, None)
    if defs:
        schema = {"$defs": defs, **schema}
    return schema


remote_input = build(req_ref)
remote_output = build(resp_ref)

json.dump(
    {"input_schema": remote_input, "output_schema": remote_output},
    open("_diagnose_remote.json", "w", encoding="utf-8"),
    ensure_ascii=False,
    indent=2,
)


# ---------- 字段级结构对比 ----------
def resolve(node, defs):
    if isinstance(node, dict) and "$ref" in node:
        return defs.get(node["$ref"].rsplit("/", 1)[-1], node)
    return node


def fields(schema, defs=None, prefix=""):
    out = {}
    if not isinstance(schema, dict):
        return out
    if defs is None:
        defs = dict(schema.get("$defs", {}))
        defs.update(schema.get("definitions", {}))
    schema = resolve(schema, defs)

    def norm_type(node):
        node = resolve(node, defs)
        if not isinstance(node, dict):
            return str(node)
        t = node.get("type")
        if isinstance(t, list):
            t = tuple(sorted(x for x in t if x != "null"))
        enum_vals = node.get("enum")
        if t is None and "anyOf" in node:
            ts = set()
            for sub in node["anyOf"]:
                sub = resolve(sub, defs)
                st = sub.get("type") if isinstance(sub, dict) else None
                if st and st != "null":
                    ts.add(st)
                if isinstance(sub, dict) and sub.get("enum"):
                    enum_vals = sub["enum"]
            t = tuple(sorted(ts))
        if enum_vals:
            t = f"{t}|enum={sorted(map(str, enum_vals))}"
        extra = {k: node[k] for k in ("maxLength", "maximum", "minimum", "maxItems", "minItems", "pattern") if k in node}
        return f"{t}{' ' + json.dumps(extra, ensure_ascii=False) if extra else ''}"

    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    for name, sub in props.items():
        sub_r = resolve(sub, defs)
        path = f"{prefix}.{name}" if prefix else name
        out[path] = (norm_type(sub), name in required)
        targets = []
        if isinstance(sub_r, dict):
            targets.append(sub_r)
            for sub2 in sub_r.get("anyOf", []):
                targets.append(resolve(sub2, defs))
        for t in targets:
            if not isinstance(t, dict):
                continue
            tt = t.get("type")
            tt_set = set(tt) if isinstance(tt, list) else ({tt} if tt else set())
            if "object" in tt_set and t.get("properties"):
                out.update(fields(t, defs, path))
            if "array" in tt_set:
                items = resolve(t.get("items", {}), defs)
                if isinstance(items, dict) and items.get("type") == "object" and items.get("properties"):
                    out.update(fields(items, defs, path + "[]"))
    return out


lines = []
for key in ("input_schema", "output_schema"):
    lf = fields(local.get(key, {}))
    rf = fields(remote_input if key == "input_schema" else remote_output)
    lines.append(f"[{key}]")
    for k in sorted(set(rf) - set(lf)):
        lines.append(f"  + 新增字段 {k}: type={rf[k][0]} required={rf[k][1]}")
    for k in sorted(set(lf) - set(rf)):
        lines.append(f"  - 移除字段 {k}: type={lf[k][0]} required={lf[k][1]}")
    for k in sorted(set(lf) & set(rf)):
        if lf[k] != rf[k]:
            lines.append(f"  ~ 变更字段 {k}: local={lf[k]} remote={rf[k]}")
    if not (set(rf) - set(lf) or set(lf) - set(rf)) and all(lf[k] == rf[k] for k in set(lf) & set(rf)):
        lines.append("  (字段结构一致)")
    lines.append("")

with open("_diagnose_diff.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("\n".join(lines))
