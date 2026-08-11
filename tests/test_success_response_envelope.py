from fastapi.testclient import TestClient

from app.main import app


def test_rag_business_result_is_wrapped_once_in_standard_envelope(monkeypatch) -> None:
    business_result = {
        "groups": [],
        "standalone_dtcs": [],
        "issues": [],
        "meta": None,
        "uncertainty_note": None,
        "missing_required_info": None,
    }
    monkeypatch.setattr(
        "app.api.v1.endpoints.tools.tool_registry.invoke",
        lambda *_: business_result,
    )

    response = TestClient(app).post(
        "/api/v1/tools/dtc_grouping_service/invoke",
        json={"arguments": {"brand": "丰田"}},
        headers={"X-Trace-ID": "trace-success-001"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "code": 0,
        "message": "success",
        "data": business_result,
        "trace_id": "trace-success-001",
    }
