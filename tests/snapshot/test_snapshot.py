"""Tests for the eco_snapshot harness: manifest keying, capture, and replay.

Capture runs against a respx-mocked eco server; serve replays the resulting
directory through Starlette's TestClient. The two are chained through one
fixture so the serve tests exercise exactly what a real capture writes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import respx
from httpx import Response
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
