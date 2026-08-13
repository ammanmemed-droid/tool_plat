import json
from pathlib import Path

import pytest

from app.core.slot_extractor import extract_slots
from app.core.validation import validate_against_schema


SKILL_DIRS = [
    "dtc-context-skill",
    "dtc-grouping-skill",
    "cause-ranking-skill",
    "diagnostic-planning-skill",
    "repair-planning-skill",
]


def _load_input_schema(skill_dir: str) -> dict:
    path = Path("myskills") / skill_dir / "tool-schema.json"
    return json.loads(path.read_text(encoding="utf-8"))["input_schema"]


def _load_contract(skill_dir: str) -> dict:
    path = Path("myskills") / skill_dir / "tool-schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("skill_dir", SKILL_DIRS)
def test_five_tool_contract_accepts_only_rag_081_public_input(skill_dir: str) -> None:
    schema = _load_input_schema(skill_dir)
    canonical = {
        "brand": "丰田",
        "model": "汉兰达",
        "year": 2021,
        "dtc_codes": ["P0136", "P0137", "P0138"],
        "language": "en",
    }

    assert validate_against_schema(canonical, schema) is None
    assert set(schema["properties"]) == {"brand", "model", "year", "dtc_codes", "language"}
    assert set(schema["required"]) == {"brand", "dtc_codes"}
    assert schema["properties"]["model"]["default"] == ""
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize("skill_dir", SKILL_DIRS)
@pytest.mark.parametrize("model", [pytest.param(None, id="omitted"), pytest.param("", id="empty")])
def test_five_tool_contract_accepts_optional_model(skill_dir: str, model: str | None) -> None:
    schema = _load_input_schema(skill_dir)
    request = {
        "brand": "丰田",
        "dtc_codes": ["P0136"],
    }
    if model is not None:
        request["model"] = model

    assert validate_against_schema(request, schema) is None


@pytest.mark.parametrize("skill_dir", SKILL_DIRS)
def test_five_tool_contract_accepts_missing_or_null_year(skill_dir: str) -> None:
    schema = _load_input_schema(skill_dir)
    request = {
        "brand": "丰田",
        "model": "汉兰达",
        "year": None,
        "dtc_codes": ["P0136"],
    }

    assert validate_against_schema(request, schema) is None


@pytest.mark.parametrize("skill_dir", SKILL_DIRS)
@pytest.mark.parametrize("invalid_year", [1899, 2101])
def test_five_tool_contract_rejects_year_outside_supported_range(
    skill_dir: str,
    invalid_year: int,
) -> None:
    schema = _load_input_schema(skill_dir)
    request = {
        "brand": "丰田",
        "model": "汉兰达",
        "year": invalid_year,
        "dtc_codes": ["P0136"],
    }

    assert validate_against_schema(request, schema) is not None


@pytest.mark.parametrize("skill_dir", SKILL_DIRS)
def test_five_tool_contract_extracts_rag_request_from_orchestration_snapshot(skill_dir: str) -> None:
    schema = _load_input_schema(skill_dir)
    snapshot = {
        "request_id": "request-001",
        "session_id": "session-001",
        "model": "auto",
        "vehicle_info": {
            "brand": "丰田",
            "model": "汉兰达",
            "year": "2021",
        },
        "system_dtc_groups": [
            {
                "dtc_codes": [
                    {"dtc_code": "p0136"},
                    {"dtc_code": "P0137"},
                    {"dtc_code": "P0136"},
                ]
            }
        ],
        "language": "en",
    }

    extracted = extract_slots(snapshot, schema)

    assert extracted == {
        "brand": "丰田",
        "model": "汉兰达",
        "year": 2021,
        "dtc_codes": ["P0136", "P0137"],
        "language": "en",
    }
    assert validate_against_schema(extracted, schema) is None


@pytest.mark.parametrize("skill_dir", SKILL_DIRS)
def test_five_tool_output_contract_uses_rag_080_status_and_no_nulls(
    skill_dir: str,
) -> None:
    output_schema = _load_contract(skill_dir)["output_schema"]
    properties = output_schema["properties"]

    assert properties["status"]["enum"] == ["ok", "no_data", "partial", "missing_input"]
    assert properties["message"]["type"] == "string"
    assert "status" in output_schema["required"]
    assert "message" in output_schema["required"]
    assert '"type": "null"' not in json.dumps(output_schema, ensure_ascii=False)


@pytest.mark.parametrize(
    "skill_dir",
    ["cause-ranking-skill", "diagnostic-planning-skill", "repair-planning-skill"],
)
def test_rag_080_group_level_outputs_allow_group_to_be_omitted(skill_dir: str) -> None:
    output_schema = _load_contract(skill_dir)["output_schema"]

    assert "group" not in output_schema["required"]
