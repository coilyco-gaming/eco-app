"""Tests for the eco-replay `/api/v1/events/stats` proxy (issue #27).

Covers the mock-data fallback and the upstream path (respx-stubbed), matching
the mod's `{ ready, total }` shape and the `X-API-Key` pass-through of the
events proxy.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from eco_replay import main
from eco_replay.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_stats_mock_fallback(client: TestClient) -> None:
    r = client.get("/api/v1/events/stats")
    assert r.status_code == 200
    assert r.json() == {"ready": True, "total": len(main._MOCK_EVENTS)}


@respx.mock
async def test_stats_proxies_upstream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "ECO_REPLAY_DB", None)
    monkeypatch.setattr(main, "UPSTREAM_URL", "http://fake/api/v1/events")
    monkeypatch.setattr(main, "UPSTREAM_API_KEY", "secret")
    route = respx.get("http://fake/api/v1/events/stats").mock(
        return_value=httpx.Response(200, json={"ready": True, "total": 701})
    )

    result = await main.fetch_stats()

    assert result == {"ready": True, "total": 701}
    assert route.called
    assert route.calls.last.request.headers["X-API-Key"] == "secret"
