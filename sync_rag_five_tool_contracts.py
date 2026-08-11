"""从 RAG 0.7.0 运行时详情同步五工具契约，明确使用 UTF-8 解码。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx


TARGETS = {
    "dtc_context_service": Path("myskills/dtc-context-skill/tool-schema.json"),
    "dtc_grouping_service": Path("myskills/dtc-grouping-skill/tool-schema.json"),
    "cause_ranking_service": Path("myskills/cause-ranking-skill/tool-schema.json"),
    "diagnostic_planning_service": Path("myskills/diagnostic-planning-skill/tool-schema.json"),
    "repair_planning_service": Path("myskills/repair-planning-skill/tool-schema.json"),
}

EXTRACT_MAPPING = {
    "brand": ["brand", "vehicle_info.brand", "messages[].content[].text.vehicle_info.brand"],
    "model": ["vehicle_info.model", "messages[].content[].text.vehicle_info.model", "model"],
    "year": ["year", "vehicle_info.year", "messages[].content[].text.vehicle_info.year"],
    "dtc_codes": [
        "dtc_codes",
        "messages[].content[].dtc_codes",
        "system_dtc_groups[].dtc_codes[].dtc_code",
        "messages[].content[].text.system_dtc_groups[].dtc_codes[].dtc_code",
    ],
    "language": ["language"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://172.16.67.169:8000")
    return parser.parse_args()


def get_json(client: httpx.Client, url: str) -> dict:
    response = client.get(url)
    response.raise_for_status()
    return json.loads(response.content.decode("utf-8"))


def main() -> int:
    options = parse_args()
    base_url = options.base_url.rstrip("/")
    client = httpx.Client(timeout=20.0)
    openapi = get_json(client, f"{base_url}/openapi.json")
    if openapi.get("info", {}).get("version") != "0.7.0":
        raise RuntimeError(f"expected RAG 0.7.0, got {openapi.get('info', {}).get('version')}")

    for tool_name, path in TARGETS.items():
        remote = get_json(client, f"{base_url}/api/v1/tools/{tool_name}")
        if remote.get("code") != 0:
            raise RuntimeError(f"RAG tool detail failed: {tool_name}: {remote}")
        detail = remote["data"]
        local = json.loads(path.read_text(encoding="utf-8"))
        input_schema = detail["input_schema"]
        input_schema["additionalProperties"] = False
        input_schema["x-extract"] = EXTRACT_MAPPING
        local["description"] = detail["description"]
        local["input_schema"] = input_schema
        local["output_schema"] = detail["output_schema"]
        path.write_text(json.dumps(local, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[SYNCED] {tool_name} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
