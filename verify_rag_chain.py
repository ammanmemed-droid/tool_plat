"""验证 RAG 0.8.0 五工具经 Tool 中台转发的完整链路。"""
from __future__ import annotations

import argparse
import json

import httpx


def assert_no_json_null(value: object, path: str = "$") -> None:
    """递归确认中台转发后的业务 data 不包含 JSON null。"""
    if value is None:
        raise RuntimeError(f"JSON null found at {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            assert_no_json_null(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_no_json_null(item, f"{path}[{index}]")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1")
    parser.add_argument("--timeout", type=float, default=60.0)
    return parser.parse_args()


def main() -> int:
    options = parse_args()
    client = httpx.Client(timeout=options.timeout)

    def invoke(tool_name: str, arguments: dict) -> dict:
        response = client.post(
            f"{options.base_url.rstrip('/')}/tools/{tool_name}/invoke",
            json={"arguments": arguments},
            headers={"X-Trace-ID": f"verify-{tool_name}"},
        )
        body = response.json()
        if response.status_code != 200 or body.get("code") != 0:
            raise RuntimeError(
                f"{tool_name} failed: HTTP {response.status_code}, "
                f"code={body.get('code')}, message={body.get('message')}"
            )
        data = body["data"]
        assert_no_json_null(data)
        if data.get("status") not in {"ok", "partial", "no_data", "missing_input"}:
            raise RuntimeError(f"invalid business status: {data.get('status')}")
        if not isinstance(data.get("message"), str):
            raise RuntimeError("business message must be a string")
        print(f"[OK] {tool_name}: {json.dumps(data, ensure_ascii=False)[:240]}")
        return data

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
        raise RuntimeError("dtc_grouping_service returned no selectable groups")

    selected_group = {
        **full_scan,
        "dtc_codes": groups[0]["dtc_codes"],
    }
    invoke("cause_ranking_service", selected_group)
    invoke("diagnostic_planning_service", selected_group)
    invoke("repair_planning_service", selected_group)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
