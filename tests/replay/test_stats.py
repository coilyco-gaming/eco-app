"""Tests for the eco-replay JSON API (issue #27, folded into the SPA in #38).

Covers the `/v1/meta`, `/v1/events`, and `/v1/events/stats` routes over the
mock-data fallback and the upstream path (respx-stubbed), matching the mod's
`{ ready, total }` / `{ events, count }` shapes and the `X-API-Key`
pass-through of the events proxy. The Jinja HTML surface was removed in #38 —
the browser UI is now the SPA's `/replay` route consuming these endpoints.
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


def test_meta_reports_mock_data(client: TestClient) -> None:
    r = client.get("/v1/meta")
    assert r.status_code == 200
    assert r.json() == {"mockData": main.USING_MOCK}


def test_events_mock_fallback(client: TestClient) -> None:
    r = client.get("/v1/events")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == len(main._MOCK_EVENTS)
    assert {"id", "unixTime", "type", "citizen", "body"} <= body["events"][0].keys()


def test_events_filter_by_type(client: TestClient) -> None:
    r = client.get("/v1/events", params={"type": "Login"})
    assert r.status_code == 200
    events = r.json()["events"]
    assert events and all(e["type"] == "Login" for e in events)


def test_stats_mock_fallback(client: TestClient) -> None:
    r = client.get("/v1/events/stats")
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
