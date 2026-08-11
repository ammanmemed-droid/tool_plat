from types import SimpleNamespace

import app.tools.cause_ranking as cause_ranking_module


def test_cause_ranking_uses_dedicated_outer_timeout(monkeypatch) -> None:
    captured: dict = {}

    def fake_invoke(tool_name: str, path: str, arguments: dict, **kwargs: object) -> dict:
        captured.update(
            tool_name=tool_name,
            path=path,
            arguments=arguments,
            **kwargs,
        )
        return {"predictions": []}

    monkeypatch.setattr(
        cause_ranking_module,
        "get_settings",
        lambda: SimpleNamespace(cause_ranking_timeout=50.0),
        raising=False,
    )
    monkeypatch.setattr("app.tools.cause_ranking.rag_client.invoke", fake_invoke)
    arguments = {
        "brand": "丰田",
        "model": "汉兰达",
        "year": 2021,
        "dtc_codes": ["P0136", "P0137"],
        "language": "en",
    }

    cause_ranking_module.cause_ranking_service(arguments)

    assert captured == {
        "tool_name": "cause_ranking_service",
        "path": "cause-ranking",
        "arguments": arguments,
        "timeout": 50.0,
    }
