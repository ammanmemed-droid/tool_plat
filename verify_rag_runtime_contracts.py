"""调用 RAG 强类型接口并用中台本地 Schema 校验真实 0.8.0 响应。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
import jsonschema

from sync_rag_five_tool_contracts import normalize_input_schema


TOOL_CONTRACTS = {
    "dtc_context_service": ("dtc-context-skill", "dtc-context"),
    "dtc_grouping_service": ("dtc-grouping-skill", "dtc-grouping"),
    "cause_ranking_service": ("cause-ranking-skill", "cause-ranking"),
    "diagnostic_planning_service": ("diagnostic-planning-skill", "diagnostic-planning"),
    "repair_planning_service": ("repair-planning-skill", "repair-planning"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://172.16.67.169:8000")
    parser.add_argument("--timeout", type=float, default=60.0)
    return parser.parse_args()


def load_contract(skill_dir: str) -> dict:
    return json.loads(
        (Path("myskills") / skill_dir / "tool-schema.json").read_text(encoding="utf-8")
    )


def assert_no_json_null(value: object, path: str = "$") -> None:
    """递归确认 RAG 0.8.0 公开响应不包含 JSON null。"""
    if value is None:
        raise RuntimeError(f"JSON null found at {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            assert_no_json_null(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_no_json_null(item, f"{path}[{index}]")


def main() -> int:
    options = parse_args()
    client = httpx.Client(timeout=options.timeout)

    for tool_name, (skill_dir, _) in TOOL_CONTRACTS.items():
        remote = client.get(
            f"{options.base_url.rstrip('/')}/api/v1/tools/{tool_name}"
        ).json()["data"]
        local = load_contract(skill_dir)
        if local["input_schema"] != normalize_input_schema(remote["input_schema"]):
            raise RuntimeError(f"input schema drift: {tool_name}")
        if local["output_schema"] != remote["output_schema"]:
            raise RuntimeError(f"output schema drift: {tool_name}")
        print(f"[SCHEMA OK] {tool_name}")

    def invoke(tool_name: str, arguments: dict) -> dict:
        skill_dir, path = TOOL_CONTRACTS[tool_name]
        response = client.post(
            f"{options.base_url.rstrip('/')}/api/v1/tool-services/{path}",
            json=arguments,
            headers={"X-Trace-ID": f"contract-check-{tool_name}"},
        )
        response.raise_for_status()
        body = response.json()
        output_schema = load_contract(skill_dir)["output_schema"]
        validator_class = jsonschema.validators.validator_for(output_schema)
        validator_class.check_schema(output_schema)
        validator_class(output_schema).validate(body)
        assert_no_json_null(body)
        if body.get("status") not in {"ok", "partial", "no_data", "missing_input"}:
            raise RuntimeError(f"invalid business status: {body.get('status')}")
        if not isinstance(body.get("message"), str):
            raise RuntimeError("business message must be a string")
        print(f"[OK] {tool_name}: HTTP {response.status_code}")
        return body

    full_scan = {
        "brand": "丰田",
        "model": "汉兰达",
        "year": 2021,
        "dtc_codes": ["P0136", "P0137", "P0138", "P0420"],
        "language": "en",
    }
    invoke("dtc_context_service", full_scan)
    grouping = invoke("dtc_grouping_service", full_scan)
    groups = grouping.get("groups") or []
    if not groups:
        raise RuntimeError("RAG grouping response has no selectable group")

    selected_group = {**full_scan, "dtc_codes": groups[0]["dtc_codes"]}
    invoke("cause_ranking_service", selected_group)
    invoke("diagnostic_planning_service", selected_group)
    invoke("repair_planning_service", selected_group)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
