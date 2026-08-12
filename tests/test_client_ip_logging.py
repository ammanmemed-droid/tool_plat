"""请求完成日志输出来源 IP（client_ip）的验收测试。

需求：日志中输出调用方 IP。
实现：请求完成摘要（http.request.completed / tool.invoke.completed）新增
client_ip 字段，取 TCP 层对端地址（request.client.host），不读请求头，
避免 X-Forwarded-For 伪造问题。
"""
import pytest
from fastapi.testclient import TestClient

from app.core.logging_config import EXTRA_FIELD_TYPES, JsonFormatter
from app.main import app


def _completed_records(caplog):
    """收集完成摘要日志记录（http.request.completed / tool.invoke.completed）。"""
    return [
        r
        for r in caplog.records
        if getattr(r, "event", None) in ("http.request.completed", "tool.invoke.completed")
    ]


def test_completed_log_contains_client_ip(caplog) -> None:
    """普通请求完成日志带 client_ip，值为 TCP 对端（TestClient 为 testclient）。"""
    with caplog.at_level("INFO", logger="app"):
        response = TestClient(app).get("/openapi.json")

    assert response.status_code == 200
    records = _completed_records(caplog)
    assert records, "应输出一条请求完成日志"
    # 完成日志可能有异常重试等多条，但每条都应带 client_ip
    for record in records:
        assert getattr(record, "client_ip", None) is not None
    assert records[-1].client_ip == "testclient"


def test_invoke_completed_log_contains_client_ip(caplog, monkeypatch) -> None:
    """invoke 请求完成日志同样带 client_ip。"""
    monkeypatch.setattr(
        "app.api.v1.endpoints.tools.tool_registry.invoke",
        lambda *_: {"result": "ok"},
    )
    with caplog.at_level("INFO", logger="app"):
        response = TestClient(app).post(
            "/api/v1/tools/dtc_grouping_service/invoke",
            json={"request_id": "req-ip-001", "arguments": {"brand": "丰田"}},
        )

    assert response.status_code == 200
    records = _completed_records(caplog)
    assert records, "应输出一条请求完成日志"
    assert records[-1].client_ip == "testclient"


def test_invoke_request_log_contains_client_ip(caplog, monkeypatch) -> None:
    """收到工具调用请求日志（tool.invoke.request）也带 client_ip。"""
    monkeypatch.setattr(
        "app.api.v1.endpoints.tools.tool_registry.invoke",
        lambda *_: {"result": "ok"},
    )
    with caplog.at_level("INFO", logger="app"):
        response = TestClient(app).post(
            "/api/v1/tools/dtc_context_service/invoke",
            json={"request_id": "req-ip-002", "arguments": {"brand": "丰田"}},
        )

    assert response.status_code == 200
    request_records = [
        r for r in caplog.records if getattr(r, "event", None) == "tool.invoke.request"
    ]
    assert request_records, "应输出一条收到工具调用请求日志"
    assert request_records[-1].client_ip == "testclient"


def test_client_ip_is_whitelisted_scalar() -> None:
    """client_ip 必须在结构化日志白名单中且限定为字符串。"""
    assert EXTRA_FIELD_TYPES["client_ip"] == (str,)


def test_client_ip_serializes_in_json_output() -> None:
    """JsonFormatter 输出中包含 client_ip 字段。"""
    import logging

    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="app.main",
        level=logging.INFO,
        pathname="app/main.py",
        lineno=1,
        msg="请求完成",
        args=(),
        exc_info=None,
    )
    record.event = "http.request.completed"
    record.client_ip = "10.20.30.40"
    payload = formatter.format(record)
    assert '"client_ip": "10.20.30.40"' in payload
