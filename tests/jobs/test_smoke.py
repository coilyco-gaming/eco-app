"""End-to-end smoke tests for the jobs JSON API.

Every endpoint under the mock-data path, plus the upstream path with respx
stubbing the mod's `/api/v1/skills` response, so we catch breakage in the
row-shaping layer before it reaches the SPA's /jobs page. The fused-app
mount (public /jobs/api/v1/* paths) is covered in tests/mcp.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from eco_spec_tracker import upstream
from eco_spec_tracker.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_meta_reports_mock_data(client: TestClient) -> None:
    r = client.get("/v1/meta")
    assert r.status_code == 200
    assert r.json() == {"mockData": True}


@pytest.mark.parametrize("path", ["/v1/professions", "/v1/players", "/v1/specialties"])
def test_api_endpoints_return_list(client: TestClient, path: str) -> None:
    r = client.get(path)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert data, f"{path} returned an empty list from mock data"


def test_api_professions_shape(client: TestClient) -> None:
    r = client.get("/v1/professions")
    row = r.json()[0]
    assert {"profession", "active", "total", "players"} <= row.keys()


def test_api_players_shape(client: TestClient) -> None:
    r = client.get("/v1/players")
    row = r.json()[0]
    assert {"name", "active", "specialties"} <= row.keys()
    if row["specialties"]:
        assert {"specialty", "level", "active"} <= row["specialties"][0].keys()


def test_api_specialties_shape(client: TestClient) -> None:
    r = client.get("/v1/specialties")
    row = r.json()[0]
    assert {"specialty", "profession", "active", "total", "holders"} <= row.keys()


UPSTREAM_FIXTURE = [
    {
        "player": "alice",
        "lastSeen": "2026-05-08T12:00:00Z",  # recent: within default 7d window
        "specialties": [
            {"name": "Basic Carpentry", "level": 3, "maxLevel": 7},
            {"name": "Mining", "level": 0, "maxLevel": 7},  # filtered: level 0
        ],
    },
    {
        "player": "bob",
        "lastSeen": None,  # never logged in
        "specialties": [{"name": "Farming", "level": 2, "maxLevel": 7}],
    },
]


@respx.mock
async def test_upstream_fetch_rows_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import UTC, datetime

    monkeypatch.setattr(upstream, "UPSTREAM_URL", "http://fake/api/v1/skills")
    respx.get("http://fake/api/v1/skills").mock(
        return_value=httpx.Response(200, json=UPSTREAM_FIXTURE)
    )
    rows = await upstream.fetch_rows()
    # Level-0 row filtered out; alice has 1, bob has 1.
    assert len(rows) == 2
    by_player = {r.player for r in rows}
    assert by_player == {"alice", "bob"}
    alice_row = next(r for r in rows if r.player == "alice")
    assert alice_row.specialty == "Basic Carpentry"
    assert alice_row.level == 3
    assert alice_row.last_seen == datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
    bob_row = next(r for r in rows if r.player == "bob")
    assert bob_row.last_seen is None
    assert bob_row.active is False


def test_upstream_unset_falls_back_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upstream, "UPSTREAM_URL", None)

    async def run() -> list:
        return await upstream.fetch_rows()

    import asyncio

    rows = asyncio.run(run())
    assert rows, "mock fallback returned no rows"
