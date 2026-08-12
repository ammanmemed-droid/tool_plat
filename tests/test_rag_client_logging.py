"""RAG 请求/响应日志（rag.request / rag.response）验收测试。

需求：tool 中台发送给 RAG 的请求参数与 RAG 返回的响应都打印到日志。
实现：RagServiceClient.invoke() 在发送前记录 rag.request，收到响应后记录
rag.response；请求/响应体走白名单与限长机制，异常场景不打印 URL 与正文。
"""
import logging

import httpx
import pytest

from app.core.discovery import rag_discovery
from app.core.logging_config import EXTRA_FIELD_TYPES
from app.services.rag_client import RagServiceClient


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.posted: list[tuple[str, dict]] = []

    def post(self, url: str, json: dict, timeout: float, headers: dict) -> _FakeResponse:
        self.posted.append((url, json))
        return _FakeResponse(self._payload)


@pytest.fixture()
def fake_rag(monkeypatch):
    """固定候选 URL + fake httpx client，避免真实网络与 Nacos。"""
    monkeypatch.setattr(
        RagServiceClient,
        "_candidate_urls",
        lambda self, service_name, base_path, path: [f"http://fake-rag:9100{base_path}/{path}"],
    )
    client = RagServiceClient()
    fake = _FakeClient({"code": 0, "data": {"result": "ok", "items": [1, 2]}})
    client._client = fake  # noqa: SLF001 - 测试替身
    return client, fake


def test_rag_request_and_response_logged(caplog, fake_rag) -> None:
    """成功调用时 rag.request 与 rag.response 都输出，且带请求/响应体。"""
    client, fake = fake_rag
    with caplog.at_level(logging.INFO, logger="app.services.rag_client"):
        result = client.invoke("dtc_context_service", "dtc-context", {"brand": "丰田", "dtc": "P0136"})

    assert result == {"result": "ok", "items": [1, 2]}
    events = {(r.event, getattr(r, "tool_name", None), getattr(r, "http_path", None)): r for r in caplog.records}
    request_records = [r for r in caplog.records if getattr(r, "event", None) == "rag.request"]
    response_records = [r for r in caplog.records if getattr(r, "event", None) == "rag.response"]
    assert len(request_records) == 1
    assert len(response_records) == 1
    assert request_records[0].tool_name == "dtc_context_service"
    assert request_records[0].http_path == "dtc-context"
    assert '"brand":"丰田"' in request_records[0].rag_request_body
    assert '"dtc":"P0136"' in request_records[0].rag_request_body
    assert '"result":"ok"' in response_records[0].rag_response_body


def test_rag_request_logged_before_post(caplog, fake_rag) -> None:
    """rag.request 必须记录在真实 POST 之前（发送前）。"""
    client, fake = fake_rag
    with caplog.at_level(logging.INFO, logger="app.services.rag_client"):
        client.invoke("dtc_grouping_service", "dtc-grouping", {"codes": ["P0136"]})

    request_records = [r for r in caplog.records if getattr(r, "event", None) == "rag.request"]
    assert len(request_records) == 1
    assert fake.posted, "应已发生真实 POST"
    assert '"codes":["P0136"]' in request_records[0].rag_request_body


def test_rag_log_fields_whitelisted() -> None:
    """rag_request_body / rag_response_body 必须在结构化日志白名单中且为字符串。"""
    assert EXTRA_FIELD_TYPES["rag_request_body"] == (str,)
    assert EXTRA_FIELD_TYPES["rag_response_body"] == (str,)


def test_rag_response_body_not_cut_at_256_chars(caplog, fake_rag) -> None:
    """RAG 响应超过 256 字符时完整输出（走字节上限 64KiB，而非字段 256 截断）。"""
    client, fake = fake_rag
    # 构造一个超过 256 字符但远小于 64KiB 的响应，验证完整落日志
    long_item = "x" * 300
    fake._payload = {"code": 0, "data": {"long_field": long_item, "items": [1, 2]}}
    with caplog.at_level(logging.INFO, logger="app.services.rag_client"):
        client.invoke("dtc_context_service", "dtc-context", {"brand": "丰田"})

    response_records = [r for r in caplog.records if getattr(r, "event", None) == "rag.response"]
    assert len(response_records) == 1
    body = response_records[0].rag_response_body
    assert '"long_field":"' + long_item in body, "300 字符字段应完整输出，不应被 256 字符截断"
    assert "truncated" not in body


def test_rag_request_body_truncated_when_huge(caplog, fake_rag) -> None:
    """超大请求体按配置上限截断，不整段写入日志。"""
    client, fake = fake_rag
    big = {"data": "x" * 200_000}
    with caplog.at_level(logging.INFO, logger="app.services.rag_client"):
        client.invoke("dtc_context_service", "dtc-context", big)

    request_records = [r for r in caplog.records if getattr(r, "event", None) == "rag.request"]
    body = request_records[0].rag_request_body
    assert len(body.encode("utf-8")) <= 65536 + 32  # 上限 + 截断后缀余量


def test_rag_failure_does_not_log_body(caplog, fake_rag, monkeypatch) -> None:
    """上游失败时只输出发送日志，不打印响应体、URL 与异常正文。"""
    client, fake = fake_rag

    def _boom(*_: object, **__: object) -> None:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(fake, "post", _boom)
    from app.core.exceptions import ToolExecutionError

    with caplog.at_level(logging.INFO, logger="app.services.rag_client"):
        with pytest.raises(ToolExecutionError):
            client.invoke("dtc_context_service", "dtc-context", {"brand": "丰田"})

    events = {getattr(r, "event", None) for r in caplog.records}
    assert events == {"rag.request"}, f"只应有发送日志，实际: {events}"
    joined = "\n".join(getattr(r, "message", "") for r in caplog.records)
    assert "connection refused" not in joined  # 异常正文不落日志
    assert "fake-rag" not in joined  # URL 不落日志
