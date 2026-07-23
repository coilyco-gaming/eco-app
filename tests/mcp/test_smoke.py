"""End-to-end smoke test for the HTTP app.

Covers the public-facing routes without spinning up a real network server:
  - `/healthz` for k8s probes
  - `/` for the tiny JSON landing page
  - `/preview*.json` data endpoints with upstream mocked (happy + failure)
  - `/mcp/` returns a sensible 4xx when called without a valid MCP client
    handshake (we only care that the route is mounted and reachable)

The old HTML `/preview` card pages were removed — product UX is the SPA and
the Jinja cards live only on the MCP `_meta.ui` fragment now.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from starlette.testclient import TestClient

from eco_mcp_app import server as eco_server
from eco_mcp_app.http_app import create_app
from eco_mcp_app.server import DEFAULT_ECO_INFO_URL
from eco_replay import main as replay_main
from eco_spec_tracker import upstream as jobs_upstream


@pytest.fixture(autouse=True)
def _clear_info_cache() -> None:
    eco_server._info_cache.clear()


_FAKE_INFO: dict[str, object] = {
    "Description": "<color=green>Eco</color> via <color=blue>Sirens</color>",
    "DetailedDescription": "Test server",
    "Category": "Test",
    "DiscordAddress": "https://discord.gg/example",
    "Version": "0.13.0.2",
    "Language": "English",
    "IsPaused": False,
    "HasPassword": False,
    "AdminOnline": True,
    "OnlinePlayers": 7,
    "TotalPlayers": 67,
    "ActiveAndOnlinePlayers": 7,
    "PeakActivePlayers": 38,
    "OnlinePlayersNames": ["alice", "bob"],
    "WorldSize": "0.52 km²",
    "Plants": 96000,
    "Animals": 0,
    "Laws": 3,
    "TotalCulture": 171.0,
    "DaysRunning": 2,
    "DaysUntilMeteor": 57,
    "HasMeteor": True,
    "CollaborationLevel": "HighCollaboration",
    "GameSpeed": "Slow",
    "SimulationLevel": "Full",
    "EconomyDesc": "473 trades, 0 contracts",
    "ExhaustionActive": False,
    "ExhaustionAfterHours": 0.0,
    "ExhaustionHoursGainPerWeekday": {},
    "Playtimes": "",
    "ServerAchievementsDict": {},
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_root_serves_spa_or_build_hint(client: TestClient) -> None:
    # With a frontend build present (frontend/dist, as in the Docker image)
    # the root serves the React SPA; without one there's no HTML surface, so
    # it returns a 404 build hint (the old /preview redirect was removed).
    r = client.get("/", follow_redirects=False)
    if Path("frontend/dist/index.html").is_file():
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
    else:
        assert r.status_code == 404
        assert "frontend-build" in r.text


def test_service_discovery(client: TestClient) -> None:
    # The service-discovery blob moved off `/info` (now the SPA's Info page) to
    # the `/api`-style path (eco-app#96).
    r = client.get("/api/service")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "eco-app"
    assert body["self"] == "/api/service"
    assert body["mcp"] == "/mcp/"
    assert body["jobs"] == "/jobs"
    assert body["jobsApi"] == "/jobs/api/v1"
    assert body["previewJson"] == "/preview.json"
    # Only the .json data plane is advertised now (the HTML preview is gone).
    assert "preview" not in body
    assert "previewTools" not in body
    assert all(p.endswith(".json") and p.startswith("/preview/") for p in body["previewToolsJson"])


def test_jobs_mount(client: TestClient) -> None:
    """The jobs JSON API (eco_spec_tracker) serves through the /jobs/api mount."""
    r = client.get("/jobs/api/v1/meta")
    assert r.status_code == 200
    assert r.json() == {"mockData": True}


def test_replay_mount(client: TestClient) -> None:
    """The replay JSON API (eco_replay) serves through the /replay/api mount."""
    meta = client.get("/replay/api/v1/meta")
    assert meta.status_code == 200
    assert meta.json() == {"mockData": True}
    events = client.get("/replay/api/v1/events")
    assert events.status_code == 200
    body = events.json()
    assert body["count"] >= 1
    assert {"id", "unixTime", "type", "citizen", "body"} <= body["events"][0].keys()


@respx.mock
def test_mounted_jobs_and_replay_use_distinct_upstreams(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One fused process keeps jobs skills and replay events independently addressed."""
    monkeypatch.setattr(jobs_upstream, "UPSTREAM_URL", "http://jobs.test/api/v1/skills")
    monkeypatch.setattr(replay_main, "ECO_REPLAY_DB", None)
    monkeypatch.setattr(replay_main, "ECO_REPLAY_UPSTREAM_URL", "http://replay.test/api/v1/events")
    jobs_route = respx.get("http://jobs.test/api/v1/skills").mock(
        return_value=httpx.Response(200, json=[{"player": "Kai", "specialties": []}])
    )
    events_route = respx.get("http://replay.test/api/v1/events").mock(
        return_value=httpx.Response(200, json={"events": [{"id": 7, "type": "Login"}]})
    )
    stats_route = respx.get("http://replay.test/api/v1/events/stats").mock(
        return_value=httpx.Response(200, json={"ready": True, "total": 7})
    )

    jobs = client.get("/jobs/api/v1/players")
    events = client.get("/replay/api/v1/events?limit=3")
    stats = client.get("/replay/api/v1/events/stats")

    assert jobs.status_code == 200
    assert events.json() == {"events": [{"id": 7, "type": "Login"}], "count": 1}
    assert stats.json() == {"ready": True, "total": 7}
    assert jobs_route.called
    assert events_route.called
    assert stats_route.called


@respx.mock
def test_preview_tool_requires_json_suffix(client: TestClient) -> None:
    # The dev HTML card route was removed; only the `.json` data endpoint is
    # served. The bare tool path is rejected at the route (it does not fall
    # through to a Jinja card). `/preview` and `/preview-map` are no longer
    # special routes — they fall to the SPA catch-all like any client path.
    r = client.get("/preview/get_eco_server_status")
    assert r.status_code == 404
    assert r.json()["error"]


@respx.mock
def test_preview_json_returns_payload(client: TestClient) -> None:
    respx.get(DEFAULT_ECO_INFO_URL).mock(return_value=httpx.Response(200, json=_FAKE_INFO))
    r = client.get("/preview.json")
    assert r.status_code == 200
    body = r.json()
    # Payload shape comes from to_payload(); just sanity-check it's structured
    # data, not HTML, and that redaction still applies.
    assert isinstance(body, dict)
    assert "alice" not in r.text
    assert "<html" not in r.text.lower()


@respx.mock
def test_preview_json_upstream_error(client: TestClient) -> None:
    respx.get(DEFAULT_ECO_INFO_URL).mock(side_effect=httpx.ConnectError("refused"))
    r = client.get("/preview.json")
    assert r.status_code == 502
    assert "error" in r.json()


@respx.mock
def test_preview_tool_json_suffix(client: TestClient) -> None:
    respx.get(DEFAULT_ECO_INFO_URL).mock(return_value=httpx.Response(200, json=_FAKE_INFO))
    r = client.get("/preview/get_eco_server_status.json")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)
    assert "<html" not in r.text.lower()


@respx.mock
def test_preview_json_forwards_server_arg(client: TestClient) -> None:
    route = respx.get("http://eco.example.com:5679/info").mock(
        return_value=httpx.Response(200, json=_FAKE_INFO)
    )
    r = client.get("/preview.json", params={"server": "eco.example.com:5679"})
    assert r.status_code == 200
    assert route.called


def test_mcp_mount_reachable() -> None:
    # No valid MCP handshake — we just want to prove the route is mounted
    # (not a 404). Using TestClient as context manager to engage lifespan,
    # which starts the StreamableHTTPSessionManager task group.
    with TestClient(create_app()) as c:
        r = c.get("/mcp/")
        assert r.status_code != 404
