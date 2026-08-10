"""一次性脚本：远端 diagnoses 契约与本地契约的全量递归差异（含描述）。"""
import json

remote = json.load(open("_diagnose_remote.json", encoding="utf-8"))
local = json.load(open("myskills/diagnose-skill/tool-schema.json", encoding="utf-8"))


def walk(lv, rv, path=""):
    diffs = []
    if isinstance(lv, dict) and isinstance(rv, dict):
        for k in sorted(set(lv) | set(rv)):
            p = f"{path}.{k}" if path else k
            if k not in lv:
                diffs.append(f"+ {p} (remote only): {json.dumps(rv[k], ensure_ascii=False)[:150]}")
            elif k not in rv:
                diffs.append(f"- {p} (local only): {json.dumps(lv[k], ensure_ascii=False)[:150]}")
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
    lines.extend(walk(local.get(key), remote.get(key), key))
    lines.append("")

with open("_diagnose_full_diff.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("\n".join(lines) if lines else "(无差异)")
