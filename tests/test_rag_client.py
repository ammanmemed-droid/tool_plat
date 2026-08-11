import httpx
import pytest

from app.core.responses import trace_id_ctx
from app.services.rag_client import RagServiceClient


class _JsonResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"groups": [], "issues": []}


def test_rag_client_forwards_current_trace_id(monkeypatch) -> None:
    client = RagServiceClient()
    captured: dict = {}

    def fake_post(url: str, **kwargs: object) -> _JsonResponse:
        captured.update(url=url, **kwargs)
        return _JsonResponse()

    monkeypatch.setattr(client, "_candidate_urls", lambda *_: ["http://rag/tool"])
    monkeypatch.setattr(client._client, "post", fake_post)
    token = trace_id_ctx.set("trace-001")
    try:
        result = client.invoke("dtc_grouping_service", "dtc-grouping", {"brand": "丰田"})
    finally:
        trace_id_ctx.reset(token)

    assert result == {"groups": [], "issues": []}
    assert captured["headers"] == {"X-Trace-ID": "trace-001"}


@pytest.mark.parametrize(
    ("http_status", "expected_code"),
    [(502, 50200), (503, 50300), (504, 50400)],
)
def test_rag_client_preserves_documented_upstream_error_code(
    monkeypatch, http_status: int, expected_code: int
) -> None:
    client = RagServiceClient()
    response = httpx.Response(
        http_status,
        request=httpx.Request("POST", "http://rag/tool"),
        json={"code": expected_code, "message": "upstream unavailable", "data": None},
    )
    monkeypatch.setattr(client, "_candidate_urls", lambda *_: ["http://rag/tool"])
    monkeypatch.setattr(client._client, "post", lambda *_, **__: response)

    with pytest.raises(Exception) as caught:
        client.invoke("dtc_grouping_service", "dtc-grouping", {"brand": "丰田"})

    assert getattr(caught.value, "code", None) == expected_code


def test_rag_client_maps_its_own_read_timeout_to_50400(monkeypatch) -> None:
    client = RagServiceClient()
    monkeypatch.setattr(client, "_candidate_urls", lambda *_: ["http://rag/tool"])

    def time_out(*_: object, **__: object) -> None:
        raise httpx.ReadTimeout(
            "read timed out",
            request=httpx.Request("POST", "http://rag/tool"),
        )

    monkeypatch.setattr(client._client, "post", time_out)

    with pytest.raises(Exception) as caught:
        client.invoke("cause_ranking_service", "cause-ranking", {"brand": "丰田"}, timeout=50.0)

    assert getattr(caught.value, "code", None) == 50400
