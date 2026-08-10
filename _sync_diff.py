"""一次性脚本：结构化对比远端与本地契约（忽略 anyOf/title/default 等表示差异，只看字段与类型）。

结果写入 _sync_diff.txt（UTF-8）。
"""
import glob
import json

remote = json.load(open("_remote_contracts.json", encoding="utf-8"))


def resolve(node, defs):
    """解析本地 $ref（#/$defs/X 或 #/definitions/X）。"""
    if isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        name = ref.rsplit("/", 1)[-1]
        return defs.get(name, node)
    return node


def fields(schema, defs=None, prefix=""):
    """提取 {字段路径: (类型, 是否必填)} 扁平映射。类型归一化：anyOf/多 type 取非 null 类型集合。"""
    out = {}
    if not isinstance(schema, dict):
        return out
    if defs is None:
        defs = {}
        for k in ("$defs", "definitions"):
            defs.update(schema.get(k, {}))
    schema = resolve(schema, defs)
    if not isinstance(schema, dict):
        return out

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
        return str(t)

    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    for name, sub in props.items():
        sub_r = resolve(sub, defs)
        path = f"{prefix}.{name}" if prefix else name
        out[path] = (norm_type(sub), name in required)
        # 递归 object / array<object>
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
for path in sorted(glob.glob("myskills/*/tool-schema.json")):
    local = json.load(open(path, encoding="utf-8"))
    name = local["tool_name"]
    r = remote.get(name)
    if not isinstance(r, dict):
        lines.append(f"### {name}: REMOTE MISSING")
        continue
    lines.append(f"### {name}")
    for key in ("input_schema", "output_schema"):
        lf = fields(local.get(key, {}))
        rf = fields(r.get(key, {}))
        added = sorted(set(rf) - set(lf))
        removed = sorted(set(lf) - set(rf))
        changed = sorted(
            k for k in set(lf) & set(rf)
            if lf[k][0] != rf[k][0] or lf[k][1] != rf[k][1]
        )
        lines.append(f"  [{key}]")
        for k in added:
            lines.append(f"    + 新增字段 {k}: type={rf[k][0]} required={rf[k][1]}")
        for k in removed:
            lines.append(f"    - 移除字段 {k}: type={lf[k][0]} required={lf[k][1]}")
        for k in changed:
            lines.append(f"    ~ 变更字段 {k}: local={lf[k]} remote={rf[k]}")
        if not (added or removed or changed):
            lines.append("    (字段结构一致)")
    lines.append("")

with open("_sync_diff.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("written", len(lines), "lines")
