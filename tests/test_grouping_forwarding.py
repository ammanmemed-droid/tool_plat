from pathlib import Path

from app.core.registry import ToolRegistry
from app.tools.dtc_grouping import dtc_grouping_service


def test_grouping_forwards_one_canonical_request_without_context_enrichment(monkeypatch) -> None:
    calls: list[tuple[str, str, dict]] = []

    def fake_invoke(tool_name: str, path: str, arguments: dict, **_: object) -> dict:
        calls.append((tool_name, path, arguments))
        return {
            "groups": [],
            "standalone_dtcs": [],
            "issues": [],
            "meta": None,
            "uncertainty_note": None,
            "missing_required_info": None,
        }

    monkeypatch.setattr("app.tools.dtc_grouping.rag_client.invoke", fake_invoke)
    registry = ToolRegistry()
    registry.register("dtc_grouping_service", dtc_grouping_service)
    registry.load_contracts(Path("myskills"))

    result = registry.invoke(
        "dtc_grouping_service",
        {
            "brand": "丰田",
            "model": "汉兰达",
            "year": 2021,
            "dtc_codes": ["P0136", "P0137"],
            "language": "en",
        },
    )

    assert result["groups"] == []
    assert calls == [
        (
            "dtc_grouping_service",
            "dtc-grouping",
            {
                "brand": "丰田",
                "model": "汉兰达",
                "year": 2021,
                "dtc_codes": ["P0136", "P0137"],
                "language": "en",
            },
        )
    ]
