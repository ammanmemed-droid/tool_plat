from app.core.registry import ToolRegistry


def test_invoke_extracts_canonical_rag_arguments_before_validation() -> None:
    received: dict = {}

    def handler(arguments: dict) -> dict:
        received.update(arguments)
        return {"ok": True}

    registry = ToolRegistry()
    registry.register("sample_rag_tool", handler)
    tool = registry.get_tool("sample_rag_tool")
    tool.input_schema = {
        "type": "object",
        "required": ["brand", "model", "dtc_codes"],
        "additionalProperties": False,
        "properties": {
            "brand": {"type": "string"},
            "model": {"type": "string"},
            "year": {"type": ["integer", "null"]},
            "dtc_codes": {
                "type": "array",
                "items": {"type": "string"},
                "uniqueItems": True,
            },
            "language": {"type": "string"},
        },
        "x-extract": {
            "brand": ["vehicle_info.brand", "brand"],
            "model": ["vehicle_info.model", "model"],
            "year": ["vehicle_info.year", "year"],
            "dtc_codes": ["system_dtc_groups[].dtc_codes[].dtc_code", "dtc_codes"],
            "language": ["language"],
        },
    }

    result = registry.invoke(
        "sample_rag_tool",
        {
            "request_id": "request-001",
            "model": "auto",
            "vehicle_info": {
                "brand": " 丰田 ",
                "model": " 汉兰达 ",
                "year": "2021",
            },
            "system_dtc_groups": [
                {
                    "dtc_codes": [
                        {"dtc_code": "p0136"},
                        {"dtc_code": " P0137 "},
                        {"dtc_code": "P0136"},
                    ]
                }
            ],
            "language": "en",
        },
    )

    assert result == {"ok": True}
    assert received == {
        "brand": "丰田",
        "model": "汉兰达",
        "year": 2021,
        "dtc_codes": ["P0136", "P0137"],
        "language": "en",
    }
