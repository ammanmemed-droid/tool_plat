import json
import re
from pathlib import Path

import pytest

from app.core.validation import validate_against_schema


EXAMPLES = {
    "dtc_context_service": ("dtc-context-skill", "dtc_context_invoke.json"),
    "dtc_grouping_service": ("dtc-grouping-skill", "dtc_grouping_invoke.json"),
    "cause_ranking_service": ("cause-ranking-skill", "cause_ranking_invoke.json"),
    "diagnostic_planning_service": ("diagnostic-planning-skill", "diagnostic_planning_invoke.json"),
    "repair_planning_service": ("repair-planning-skill", "repair_planning_invoke.json"),
}


def _assert_no_null(value: object, path: str = "$") -> None:
    if value is None:
        pytest.fail(f"JSON null found at {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_no_null(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_null(item, f"{path}[{index}]")


def _read_documented_responses() -> dict[str, dict]:
    readme = (Path("examples/orchestrator") / "README.md").read_text(encoding="utf-8")
    blocks = [json.loads(block) for block in re.findall(r"```json\s*\n(.*?)\n```", readme, re.S)]
    assert len(blocks) == len(EXAMPLES) * 2
    return {
        tool_name: blocks[index * 2 + 1]
        for index, tool_name in enumerate(EXAMPLES)
    }


@pytest.mark.parametrize(("tool_name", "paths"), EXAMPLES.items())
def test_orchestrator_example_satisfies_published_tool_contract(
    tool_name: str, paths: tuple[str, str]
) -> None:
    skill_dir, example_name = paths
    contract = json.loads(
        (Path("myskills") / skill_dir / "tool-schema.json").read_text(encoding="utf-8")
    )
    request = json.loads(
        (Path("examples/orchestrator") / example_name).read_text(encoding="utf-8")
    )

    assert contract["tool_name"] == tool_name
    assert request["request_id"] == f"orchestration-{tool_name}-001"
    assert request["session_id"] == "repair-session-001"
    assert request["tenant_id"] == "tenant-demo"
    assert request["task_id"] == 1001
    assert not {"request_id", "session_id", "tenant_id", "task_id"} & set(
        request["arguments"]
    )
    assert validate_against_schema(request["arguments"], contract["input_schema"]) is None


@pytest.mark.parametrize(("tool_name", "paths"), EXAMPLES.items())
def test_documented_rag_080_response_satisfies_output_contract(
    tool_name: str, paths: tuple[str, str]
) -> None:
    skill_dir, _ = paths
    contract = json.loads(
        (Path("myskills") / skill_dir / "tool-schema.json").read_text(encoding="utf-8")
    )
    response = _read_documented_responses()[tool_name]
    data = response["data"]

    assert response["code"] == 0
    assert response["message"] == "success"
    assert data["status"] in {"ok", "partial", "no_data", "missing_input"}
    assert isinstance(data["message"], str)
    _assert_no_null(data)
    assert validate_against_schema(data, contract["output_schema"]) is None
