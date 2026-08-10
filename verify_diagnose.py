"""验证 diagnose_service 全链路（经 Nacos 发现转发到 roxie-rag-service）。"""
import json

import httpx

args = json.load(open("examples/diagnose_invoke.json", encoding="utf-8"))
r = httpx.post(
    "http://localhost:8000/api/v1/tools/diagnose_service/invoke",
    json=args,
    timeout=90,
)
b = r.json()
print("HTTP", r.status_code, "code:", b.get("code"), flush=True)
if b.get("code") != 0:
    print("msg:", str(b.get("message"))[:400], flush=True)
else:
    d = b["data"]
    print("request_id:", d.get("request_id"), "| elapsed_ms:", d.get("elapsed_ms"), flush=True)
    print("groups:", len(d.get("groups") or []), "| results:", len(d.get("results") or []), flush=True)
    ctx = d.get("context") or {}
    print("context.dtc_codes:", ctx.get("dtc_codes"), "| source:", ctx.get("source"), flush=True)
    if d.get("results"):
        rc = d["results"][0].get("ranked_causes") or []
        if rc:
            top = rc[0]
            print("top1:", top.get("possible_cause"), "| score:", top.get("final_score"), flush=True)
            print("top1 oem_doc:", top.get("oem_doc"), flush=True)
