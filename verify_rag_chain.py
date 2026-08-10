"""验证远程工具经 Nacos 发现转发到 roxie-rag-service 的全链路。"""
import json

import httpx

BASE = "http://localhost:8000/api/v1"
c = httpx.Client(timeout=30)


def invoke(tool: str, args: dict) -> dict:
    r = c.post(f"{BASE}/tools/{tool}/invoke", json={"arguments": args})
    b = r.json()
    if b.get("code") == 0:
        print(f"[OK] {tool} (HTTP {r.status_code})", flush=True)
    else:
        print(f"[ERR] {tool}: code={b.get('code')} msg={str(b.get('message'))[:120]}", flush=True)
    return b


# 1. dtc_context
b = invoke("dtc_context_service", {"dtc_code": "P0171", "brand": "宝马"})
print("   ", json.dumps(b.get("data"), ensure_ascii=False)[:300], flush=True)

# 2. dtc_grouping
b = invoke("dtc_grouping_service", {
    "dtc_list": ["P0171", "P0300"],
    "brand": "宝马",
    "dtc_entries": [
        {"dtc_code": "P0171", "system": "发动机系统", "related_parts": ["真空管路", "MAF 空气流量传感器"]},
        {"dtc_code": "P0300", "system": "发动机系统", "related_parts": ["火花塞", "真空管路"]},
    ],
})
print("   ", json.dumps(b.get("data"), ensure_ascii=False)[:300], flush=True)

# 3. cause_ranking
b = invoke("cause_ranking_service", {
    "operation": "retrieve_causes", "target_type": "single_dtc",
    "dtcs": ["P0171"], "brand": "宝马",
})
print("   ", json.dumps(b.get("data"), ensure_ascii=False)[:300], flush=True)

# 4. diagnostic_planning
b = invoke("diagnostic_planning_service", {
    "operation": "retrieve_checks", "target_type": "single_dtc",
    "dtcs": ["P0171"], "brand": "宝马",
})
print("   ", json.dumps(b.get("data"), ensure_ascii=False)[:300], flush=True)

# 5. repair_planning
b = invoke("repair_planning_service", {
    "repair_target": {"target_name": "进气系统真空泄漏", "target_status": "confirmed"},
    "brand": "宝马",
})
print("   ", json.dumps(b.get("data"), ensure_ascii=False)[:300], flush=True)

# 6. maintenance_light_reset 仍为本地实现
b = invoke("maintenance_light_reset_service", {"brand": "奔驰", "model": "C200", "year": "2010"})
print("   ", json.dumps(b.get("data"), ensure_ascii=False)[:300], flush=True)
