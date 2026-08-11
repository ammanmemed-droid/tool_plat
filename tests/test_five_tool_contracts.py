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


@pytest.mark.parametrize("skill_dir", SKILL_DIRS)
def test_five_tool_contract_accepts_only_rag_070_public_input(skill_dir: str) -> None:
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
    assert set(schema["required"]) == {"brand", "model", "dtc_codes"}
    assert schema["additionalProperties"] is False


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
