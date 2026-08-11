import json
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
    assert validate_against_schema(request["arguments"], contract["input_schema"]) is None
