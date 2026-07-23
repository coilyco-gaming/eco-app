"""Tests for the eco_snapshot harness: manifest keying, capture, and replay.

Capture runs against a respx-mocked eco server; serve replays the resulting
directory through Starlette's TestClient. The two are chained through one
fixture so the serve tests exercise exactly what a real capture writes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import respx
from httpx import Request, Response
from starlette.testclient import TestClient

from eco_snapshot.capture import capture_snapshot
from eco_snapshot.manifest import Manifest, request_key, resource_key
from eco_snapshot.serve import build_app

BASE = "http://eco.test:3001"

FLATLIST = [
    {"Name": "Currency in Circulation", "IsAction": False},
    {"Name": "CurrencyTrade", "IsAction": True},
]
SERIES = {"Times": [0, 86400], "Values": [10.0, 12.5], "Interval": 86400, "Unit": "$"}
ACTIONS_CSV = "Time,Citizen,Currency\n100,7,Sirens\n"
SPECIES_CSV = "Time,Population\n0,42\n"
EVENTS = [{"id": 1, "type": "Login", "citizen": "Kai"}]
WORLDLAYERS = [
    {
        "Category": "Biome",
        "List": [
            {"LayerName": "TaigaBiome", "Summary": "20%"},
            {"LayerName": "DesertBiome", "Summary": "10%"},
        ],
    },
    {"Category": "World", "List": [{"LayerName": "Altitude", "Summary": "0"}]},
]


def test_request_key_sorts_params() -> None:
    assert request_key("/datasets/get", "dayEnd=5&dataset=X&dayStart=0") == request_key(
        "/datasets/get", [("dataset", "X"), ("dayStart", "0"), ("dayEnd", "5")]
    )
    assert request_key("/info") == "/info"


def test_resource_key_keeps_only_significant_params() -> None:
    assert resource_key("/datasets/get", "dataset=X&dayEnd=5") == resource_key(
        "/datasets/get", "dataset=X&dayEnd=999&dayStart=3"
    )
    assert resource_key("/api/v1/exporter/actions", "actionName=CurrencyTrade") is not None
    # Paths with no declared significant params opt out of loose matching.
    assert resource_key("/info", "") is None
    assert resource_key("/api/v1/users", "anything=1") is None


@pytest.fixture
async def snapshot_dir(tmp_path: Path) -> Path:
    with respx.mock:
        respx.get(f"{BASE}/info").respond(json={"DaysRunning": 56.4})
        respx.get(f"{BASE}/datasets/flatlist").respond(json=FLATLIST)
        respx.get(f"{BASE}/datasets/get", params={"dataset": "Currency in Circulation"}).respond(
            json=SERIES
        )
        respx.get(
            f"{BASE}/api/v1/exporter/actions", params={"actionName": "CurrencyTrade"}
        ).respond(text=ACTIONS_CSV, headers={"content-type": "text/csv"})
        respx.get(f"{BASE}/api/v1/exporter/specieslist").respond(
            text="Agave\nBison\n", headers={"content-type": "text/plain"}
        )
        respx.get(f"{BASE}/api/v1/exporter/species").respond(
            text=SPECIES_CSV, headers={"content-type": "text/csv"}
        )
        respx.get(f"{BASE}/api/v1/worldlayers/layers").respond(json=WORLDLAYERS)
        respx.get(f"{BASE}/Layers/TaigaBiome.gif").respond(
            content=b"taiga", headers={"content-type": "image/gif"}
        )
        respx.get(f"{BASE}/Layers/DesertBiome.gif").respond(
            content=b"desert", headers={"content-type": "image/gif"}
        )
        respx.get(f"{BASE}/Layers/Altitude.gif").respond(
            content=b"altitude", headers={"content-type": "image/gif"}
        )
        respx.get(f"{BASE}/api/v1/events", params={"limit": "1000"}).respond(json=EVENTS)
        # Everything else this server "doesn't expose" - captured as failures.
        respx.route().mock(return_value=Response(404))

        manifest = await capture_snapshot(BASE, tmp_path, api_key="test-key")

    assert manifest.entries, "capture wrote nothing"
    return tmp_path


async def test_capture_writes_manifest_and_bytes(snapshot_dir: Path) -> None:
    manifest = Manifest.load(snapshot_dir)
    assert manifest.day_end == 57  # ceil(56.4)
    assert manifest.base_url == BASE

    by_key = {e.key: e for e in manifest.entries}
    series_key = request_key(
        "/datasets/get",
        [("dataset", "Currency in Circulation"), ("dayStart", "0"), ("dayEnd", "57")],
    )
    assert series_key in by_key
    csv_entry = by_key[request_key("/api/v1/exporter/actions", "actionName=CurrencyTrade")]
    assert (snapshot_dir / csv_entry.file).read_text() == ACTIONS_CSV
    assert csv_entry.file.endswith(".csv")

    # The species fan-out came from the newline-delimited specieslist.
    assert request_key("/api/v1/exporter/species", "speciesName=Agave") in by_key
    assert request_key("/api/v1/exporter/species", "speciesName=Bison") in by_key

    # Every raster the live catalog names is captured, not only the built-in
    # preview/pollution pair.
    for layer, expected in {
        "TaigaBiome": b"taiga",
        "DesertBiome": b"desert",
        "Altitude": b"altitude",
    }.items():
        entry = by_key[request_key(f"/Layers/{layer}.gif")]
        assert (snapshot_dir / entry.file).read_bytes() == expected

    # Unexposed endpoints are recorded, not silently skipped.
    failed_paths = {f["path"] for f in manifest.failures}
    assert "/api/v1/stores" in failed_paths


async def test_serve_replays_exact_and_loose_matches(snapshot_dir: Path) -> None:
    client = TestClient(build_app(snapshot_dir))

    assert client.get("/info").json()["DaysRunning"] == 56.4

    # Volatile day window differs from capture time - significant-param
    # matching must still find the series.
    r = client.get(
        "/datasets/get",
        params={"dataset": "Currency in Circulation", "dayStart": 0, "dayEnd": 999},
    )
    assert r.json() == SERIES

    r = client.get("/api/v1/exporter/actions", params={"actionName": "CurrencyTrade"})
    assert r.text == ACTIONS_CSV
    assert r.headers["content-type"].startswith("text/csv")

    # Single-entry path with a query the capture never used: path-only fallback.
    assert client.get("/api/v1/events", params={"limit": 5}).json() == EVENTS

    missing = client.get("/api/v1/stores")
    assert missing.status_code == 404
    assert missing.json()["error"] == "not in snapshot"

    meta = client.get("/_snapshot").json()
    assert meta["day_end"] == 57
    assert meta["entries"] == len(Manifest.load(snapshot_dir).entries)


async def test_capture_pages_every_replay_event(tmp_path: Path) -> None:
    """A 1,000-row replay page is followed through its exclusive id cursor."""
    first_page = [{"id": event_id} for event_id in range(2_000, 1_000, -1)]
    second_page = [{"id": event_id} for event_id in range(1_000, 0, -1)]

    def events_page(request: Request) -> Response:
        before_id = request.url.params.get("beforeId")
        if before_id is None:
            return Response(200, json={"events": first_page, "count": len(first_page)})
        if before_id == "1001":
            return Response(200, json={"events": second_page, "count": len(second_page)})
        if before_id == "1":
            return Response(200, json={"events": [], "count": 0})
        return Response(400)

    with respx.mock:
        respx.get(f"{BASE}/info").respond(json={"DaysRunning": 1})
        respx.get(f"{BASE}/datasets/flatlist").respond(json=[])
        respx.get(f"{BASE}/api/v1/exporter/specieslist").respond(text="")
        respx.get(f"{BASE}/api/v1/worldlayers/layers").respond(json=[])
        respx.get(f"{BASE}/api/v1/events").mock(side_effect=events_page)
        respx.route().mock(return_value=Response(404))

        manifest = await capture_snapshot(BASE, tmp_path)

    event_entries = [entry for entry in manifest.entries if entry.path == "/api/v1/events"]
    assert [entry.query for entry in event_entries] == [
        "limit=1000",
        "beforeId=1001&limit=1000",
        "beforeId=1&limit=1000",
    ]
    assert not [failure for failure in manifest.failures if failure["path"] == "/api/v1/events"]

    # The fixture can still resolve a regular first-page app request even
    # though the snapshot now holds several cursor pages.
    client = TestClient(build_app(tmp_path))
    assert client.get("/api/v1/events", params={"limit": 100}).json()["events"][0]["id"] == 2_000
