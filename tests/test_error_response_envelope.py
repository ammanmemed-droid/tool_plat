import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import ToolPlatformError
from app.main import app


@pytest.mark.parametrize(
    ("business_code", "http_status"),
    [(50200, 502), (50300, 503), (50400, 504)],
)
def test_upstream_error_response_keeps_standard_envelope(
    monkeypatch, business_code: int, http_status: int
) -> None:
    def fail(*_: object, **__: object) -> dict:
        raise ToolPlatformError("RAG unavailable", code=business_code)

    monkeypatch.setattr("app.api.v1.endpoints.tools.tool_registry.invoke", fail)
    response = TestClient(app).post(
        "/api/v1/tools/dtc_grouping_service/invoke",
        json={"arguments": {"brand": "丰田"}},
        headers={"X-Trace-ID": "trace-001"},
    )

    assert response.status_code == http_status
    assert response.json() == {
        "code": business_code,
        "message": "RAG unavailable",
        "data": None,
        "trace_id": "trace-001",
    }
