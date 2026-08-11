from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.core.responses as responses
from app.api.v1.schemas import ToolInvokeRequest
from app.main import app


def test_extract_echo_ids_matches_only_top_level_snake_case_ids() -> None:
    assert hasattr(responses, "extract_echo_ids"), "echo ID extractor is missing"

    payload = {
        "id": 7,
        "request_id": "req-1",
        "tenant_id": "tenant-1",
        "trace_id": "body-trace",
        "requestId": "not-matched",
        "arguments": {"group_id": "business-id"},
        "nested": {"cause_id": "not-matched"},
        "optional_id": None,
    }

    assert responses.extract_echo_ids(payload) == {
        "id": 7,
        "request_id": "req-1",
        "tenant_id": "tenant-1",
        "trace_id": "body-trace",
    }


def test_flat_request_keeps_agent_ids_out_of_arguments() -> None:
    request = ToolInvokeRequest.model_validate(
        {
            "request_id": "req-1",
            "session_id": "session-1",
            "task_id": 1001,
            "brand": "丰田",
            "model": "汉兰达",
        }
    )

    assert request.arguments == {"brand": "丰田", "model": "汉兰达"}


@pytest.mark.parametrize("invalid_id", [True, {}, []])
def test_non_scalar_top_level_id_is_rejected(invalid_id: object) -> None:
    with pytest.raises(ValidationError):
        ToolInvokeRequest.model_validate(
            {
                "request_id": "req-valid",
                "session_id": invalid_id,
                "arguments": {"brand": "丰田"},
            }
        )


def test_success_echoes_all_top_level_ids_but_not_nested_ids(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.endpoints.tools.tool_registry.invoke",
        lambda *_: {"result": "ok"},
    )

    response = TestClient(app).post(
        "/api/v1/tools/dtc_context_service/invoke",
        json={
            "id": 7,
            "request_id": "req-1",
            "session_id": "session-1",
            "tenant_id": "tenant-1",
            "task_id": 1001,
            "requestId": "not-matched",
            "arguments": {
                "brand": "丰田",
                "group_id": "nested-business-id",
            },
        },
        headers={"X-Trace-ID": "header-trace"},
    )

    assert response.status_code == 200
    assert response.json()["echo"] == {
        "id": 7,
        "request_id": "req-1",
        "session_id": "session-1",
        "tenant_id": "tenant-1",
        "task_id": 1001,
    }


def test_body_trace_id_is_echoed_without_overriding_envelope_trace(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.endpoints.tools.tool_registry.invoke",
        lambda *_: {"result": "ok"},
    )

    response = TestClient(app).post(
        "/api/v1/tools/dtc_context_service/invoke",
        json={
            "trace_id": "body-trace",
            "arguments": {"brand": "丰田"},
        },
        headers={"X-Trace-ID": "header-trace"},
    )

    assert response.json()["trace_id"] == "header-trace"
    assert response.json()["echo"] == {"trace_id": "body-trace"}


def test_invalid_id_type_returns_standard_invoke_error_with_valid_echo() -> None:
    response = TestClient(app).post(
        "/api/v1/tools/dtc_context_service/invoke",
        json={
            "request_id": "req-valid",
            "session_id": {},
            "arguments": {"brand": "丰田"},
        },
        headers={"X-Trace-ID": "trace-invalid-id"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == 40000
    assert response.json()["data"] is None
    assert response.json()["trace_id"] == "trace-invalid-id"
    assert response.json()["echo"] == {"request_id": "req-valid"}


def test_malformed_json_returns_empty_echo_in_standard_invoke_error() -> None:
    response = TestClient(app).post(
        "/api/v1/tools/dtc_context_service/invoke",
        content=b'{"request_id":',
        headers={
            "Content-Type": "application/json",
            "X-Trace-ID": "trace-malformed",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == 40000
    assert response.json()["data"] is None
    assert response.json()["trace_id"] == "trace-malformed"
    assert response.json()["echo"] == {}


def test_unhandled_invoke_error_keeps_echo(monkeypatch) -> None:
    def fail(*_: object, **__: object) -> dict:
        raise RuntimeError("unexpected")

    monkeypatch.setattr("app.api.v1.endpoints.tools.tool_registry.invoke", fail)
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/tools/dtc_context_service/invoke",
        json={
            "correlation_id": "corr-1",
            "arguments": {"brand": "丰田"},
        },
        headers={"X-Trace-ID": "trace-unhandled"},
    )

    assert response.status_code == 500
    assert response.json()["code"] == 50000
    assert response.json()["echo"] == {"correlation_id": "corr-1"}


def test_concurrent_invoke_requests_do_not_leak_echo(monkeypatch) -> None:
    barrier = Barrier(2)

    def overlap(_: str, arguments: dict) -> dict:
        barrier.wait(timeout=5)
        return {"brand": arguments["brand"]}

    monkeypatch.setattr("app.api.v1.endpoints.tools.tool_registry.invoke", overlap)

    def invoke(request_id: str, brand: str) -> dict:
        response = TestClient(app).post(
            "/api/v1/tools/dtc_context_service/invoke",
            json={"request_id": request_id, "arguments": {"brand": brand}},
        )
        assert response.status_code == 200
        return response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(invoke, "req-a", "丰田")
        second = pool.submit(invoke, "req-b", "宝马")
        bodies = [first.result(timeout=10), second.result(timeout=10)]

    assert {body["echo"]["request_id"] for body in bodies} == {"req-a", "req-b"}
    assert {
        (body["echo"]["request_id"], body["data"]["brand"])
        for body in bodies
    } == {("req-a", "丰田"), ("req-b", "宝马")}


def test_non_invoke_response_does_not_gain_echo() -> None:
    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert "echo" not in response.json()


def test_invoke_openapi_examples_include_echo_on_success_and_errors() -> None:
    openapi = app.openapi()
    invoke_responses = openapi["paths"][
        "/api/v1/tools/{tool_name}/invoke"
    ]["post"]["responses"]

    for status in ("200", "400", "404", "500"):
        example = invoke_responses[status]["content"]["application/json"]["example"]
        assert "echo" in example

    detail_404 = openapi["paths"]["/api/v1/tools/{tool_name}"]["get"][
        "responses"
    ]["404"]["content"]["application/json"]["example"]
    assert "echo" not in detail_404
