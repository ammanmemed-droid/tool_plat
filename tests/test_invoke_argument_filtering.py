from app.core.registry import ToolRegistry
from app.core.slot_extractor import extract_slots


def test_schema_without_x_extract_drops_unknown_agent_fields() -> None:
    schema = {
        "type": "object",
        "properties": {
            "brand": {"type": "string"},
            "model": {"type": "string"},
        },
    }

    assert extract_slots(
        {
            "brand": "丰田",
            "model": "汉兰达",
            "request_id": "req-1",
            "agent_state": {"step": 3},
        },
        schema,
    ) == {"brand": "丰田", "model": "汉兰达"}


def test_registry_handler_receives_only_declared_schema_properties() -> None:
    received: dict = {}

    def handler(arguments: dict) -> dict:
        received.update(arguments)
        return {"ok": True}

    registry = ToolRegistry()
    registry.register("plain_schema_tool", handler)
    tool = registry.get_tool("plain_schema_tool")
    tool.input_schema = {
        "type": "object",
        "required": ["brand"],
        "properties": {
            "brand": {"type": "string"},
            "model": {"type": "string"},
        },
    }

    result = registry.invoke(
        "plain_schema_tool",
        {
            "brand": "丰田",
            "model": "汉兰达",
            "session_id": "session-1",
            "agent_private_context": "not-forwarded",
        },
    )

    assert result == {"ok": True}
    assert received == {"brand": "丰田", "model": "汉兰达"}
