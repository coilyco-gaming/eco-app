"""Tests for the eco-replay JSON API (issue #27, folded into the SPA in #38).

Covers the `/v1/meta`, `/v1/events`, and `/v1/events/stats` routes over the
mock-data fallback and the dedicated replay-upstream path (respx-stubbed),
including the public-safe unavailable response for bad upstreams. The Jinja
HTML surface was removed in #38 — the browser UI is now the SPA's `/replay`
route consuming these endpoints.
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
    assert r.json() == {"mockData": main.using_mock()}


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
    monkeypatch.setattr(main, "ECO_REPLAY_UPSTREAM_URL", "http://fake/api/v1/events")
    monkeypatch.setattr(main, "UPSTREAM_API_KEY", "secret")
    route = respx.get("http://fake/api/v1/events/stats").mock(
        return_value=httpx.Response(200, json={"ready": True, "total": 701})
    )

    result = await main.fetch_stats()

    assert result == {"ready": True, "total": 701}
    assert route.called
    assert route.calls.last.request.headers["X-API-Key"] == "secret"


@respx.mock
async def test_events_proxies_dedicated_upstream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "ECO_REPLAY_DB", None)
    monkeypatch.setattr(main, "ECO_REPLAY_UPSTREAM_URL", "http://fake/api/v1/events")
    route = respx.get("http://fake/api/v1/events").mock(
        return_value=httpx.Response(200, json={"events": [{"id": 42, "type": "Login"}]})
    )

    result = await main.fetch_events(limit=3)

    assert result == [{"id": 42, "type": "Login"}]
    assert route.called
    assert route.calls.last.request.url.params["limit"] == "3"


@pytest.mark.parametrize("route_path", ["/v1/events", "/v1/events/stats"])
@pytest.mark.parametrize("status_code", [401, 404])
@respx.mock
def test_upstream_http_errors_are_structured_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    route_path: str,
    status_code: int,
) -> None:
    monkeypatch.setattr(main, "ECO_REPLAY_DB", None)
    monkeypatch.setattr(main, "ECO_REPLAY_UPSTREAM_URL", "http://fake/api/v1/events")
    suffix = "/stats" if route_path.endswith("stats") else ""
    respx.get(f"http://fake/api/v1/events{suffix}").mock(return_value=httpx.Response(status_code))

    response = client.get(route_path)

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "replay_upstream_unavailable",
            "message": "The replay chronicle is temporarily unavailable.",
        }
    }


@pytest.mark.parametrize("route_path", ["/v1/events", "/v1/events/stats"])
@respx.mock
def test_upstream_timeouts_are_structured_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    route_path: str,
) -> None:
    monkeypatch.setattr(main, "ECO_REPLAY_DB", None)
    monkeypatch.setattr(main, "ECO_REPLAY_UPSTREAM_URL", "http://fake/api/v1/events")
    suffix = "/stats" if route_path.endswith("stats") else ""
    respx.get(f"http://fake/api/v1/events{suffix}").mock(side_effect=httpx.ReadTimeout("slow"))

    response = client.get(route_path)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "replay_upstream_unavailable"


@pytest.mark.parametrize("route_path", ["/v1/events", "/v1/events/stats"])
@respx.mock
def test_malformed_upstream_responses_are_structured_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    route_path: str,
) -> None:
    monkeypatch.setattr(main, "ECO_REPLAY_DB", None)
    monkeypatch.setattr(main, "ECO_REPLAY_UPSTREAM_URL", "http://fake/api/v1/events")
    suffix = "/stats" if route_path.endswith("stats") else ""
    respx.get(f"http://fake/api/v1/events{suffix}").mock(
        return_value=httpx.Response(200, content=b"this is not JSON")
    )

    response = client.get(route_path)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "replay_upstream_unavailable"
