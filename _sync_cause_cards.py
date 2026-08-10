"""一次性脚本：提取最新 dtc-cause-cards 契约并与本地 tool-schema.json 全量对比。"""
import json
from typing import Any

openapi = json.load(open("_openapi_rag-service.json", encoding="utf-8"))
components = openapi["components"]["schemas"]
local = json.load(open("myskills/dtc-cause-cards-skill/tool-schema.json", encoding="utf-8"))

path_item = openapi["paths"]["/api/v1/dtc-cause-cards"]["post"]


def collect(schema: Any, defs: dict) -> Any:
    if isinstance(schema, dict):
        out = {}
        for k, v in schema.items():
            if k == "$ref" and isinstance(v, str) and v.startswith("#/components/schemas/"):
                name = v.rsplit("/", 1)[-1]
                if name not in defs:
                    defs[name] = None
                    defs[name] = collect(components[name], defs)
                out[k] = f"#/$defs/{name}"
            else:
                out[k] = collect(v, defs)
        return out
    if isinstance(schema, list):
        return [collect(i, defs) for i in schema]
    return schema


def build(root: dict) -> dict:
    defs: dict = {}
    schema = collect(root, defs)
    if schema.get("$ref", "").startswith("#/$defs/"):
        name = schema["$ref"].rsplit("/", 1)[-1]
        schema = dict(defs[name])
        defs.pop(name, None)
    if defs:
        schema = {"$defs": defs, **schema}
    return schema


req_ref = path_item["requestBody"]["content"]["application/json"]["schema"]
resp_ref = path_item["responses"]["200"]["content"]["application/json"]["schema"]
remote = {"input_schema": build(req_ref), "output_schema": build(resp_ref)}
remote["endpoint_meta"] = {
    "summary": path_item.get("summary"),
    "description": path_item.get("description"),
    "responses": sorted(path_item.get("responses", {}).keys()),
}
json.dump(remote, open("_cause_cards_remote.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def walk(lv, rv, path=""):
    diffs = []
    if isinstance(lv, dict) and isinstance(rv, dict):
        for k in sorted(set(lv) | set(rv)):
            p = f"{path}.{k}" if path else k
            if k not in lv:
                diffs.append(f"+ {p} (remote only): {json.dumps(rv[k], ensure_ascii=False)[:200]}")
            elif k not in rv:
                diffs.append(f"- {p} (local only): {json.dumps(lv[k], ensure_ascii=False)[:200]}")
            else:
                diffs.extend(walk(lv[k], rv[k], p))
    elif isinstance(lv, list) and isinstance(rv, list):
        if len(lv) != len(rv) or any(
            json.dumps(a, sort_keys=True, ensure_ascii=False) != json.dumps(b, sort_keys=True, ensure_ascii=False)
            for a, b in zip(lv, rv)
        ):
            diffs.append(f"~ {path}:\n    local ={json.dumps(lv, ensure_ascii=False)[:300]}\n    remote={json.dumps(rv, ensure_ascii=False)[:300]}")
    elif lv != rv:
        diffs.append(f"~ {path}:\n    local ={json.dumps(lv, ensure_ascii=False)[:300]}\n    remote={json.dumps(rv, ensure_ascii=False)[:300]}")
    return diffs


lines = []
for key in ("input_schema", "output_schema"):
    lines.append(f"===== {key} =====")
    lines.extend(walk(local.get(key), remote.get(key), key) or ["(无差异)"])
    lines.append("")

with open("_cause_cards_diff.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("\n".join(lines))
