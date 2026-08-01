"""JSON API for eco-replay (the "Kaihronicler", a Chronicler mirror).

Lists recorded player actions written by the C# Eco replay mod. Mounted at
`/replay/api` inside eco_mcp_app's ASGI app (http_app.py), so the public paths
are `/replay/api/v1/*`, mirroring the jobs tracker's `/jobs/api` mount. The
browser UI is the React SPA's `/replay` route, which consumes this API (plus
`/v1/meta` for the mock-data banner). There is no server-rendered HTML surface
here, per the repo's SPA-only rule (eco-app#38, DLT epic #37).

Three read paths, in priority order:

1. `ECO_REPLAY_FILE` env var pointing at the mod's append-only JSONL file
   (e.g. `/home/kai/Steam/steamapps/common/EcoServer/Storage/EcoReplay.jsonl`).
   Complete lines are safe to read alongside the single mod writer. A malformed
   or partial final line is ignored.
2. `ECO_REPLAY_UPSTREAM_URL` env var pointing at the mod's HTTP `/api/v1/events`
   endpoint. Eco's web server requires admin auth. Set
   `UPSTREAM_API_KEY` to pass it through as `X-API-Key`.
3. Neither set: mock data, for local UI dev without an Eco server.
"""

from __future__ import annotations

import json
import os
from collections import deque
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from eco_mcp_app.telemetry import init_telemetry

ECO_REPLAY_FILE = os.environ.get("ECO_REPLAY_FILE")
ECO_REPLAY_UPSTREAM_URL = os.environ.get("ECO_REPLAY_UPSTREAM_URL")
UPSTREAM_API_KEY = os.environ.get("UPSTREAM_API_KEY")

# Shared idempotent init from eco_mcp_app. In the fused process every
# entrypoint calls it; whichever runs first wins, the rest are no-ops.
init_telemetry()

app = FastAPI(title="eco-replay-api", version="0.2.0")


_MOCK_EVENTS = [
    {
        "id": 3,
        "unixTime": 1779000300,
        "gameTime": 100200,
        "type": "PlaceBlock",
        "citizen": "Kai",
        "body": json.dumps({"position": "(120, 64, -85)", "block": "Sandstone"}),
    },
    {
        "id": 2,
        "unixTime": 1779000200,
        "gameTime": 100100,
        "type": "ChatMessage",
        "citizen": "Mira",
        "body": json.dumps({"channel": "#general", "message": "anyone selling iron ingots?"}),
    },
    {
        "id": 1,
        "unixTime": 1779000100,
        "gameTime": 100000,
        "type": "Login",
        "citizen": "Kai",
        "body": json.dumps({}),
    },
]


class ReplayUpstreamUnavailableError(Exception):
    """The configured replay upstream could not provide a usable response."""


def using_mock() -> bool:
    """Whether replay has neither its JSONL file nor its dedicated HTTP source."""
    return ECO_REPLAY_FILE is None and ECO_REPLAY_UPSTREAM_URL is None


def _unavailable_response() -> JSONResponse:
    """Return one public-safe shape for all replay upstream failures."""
    return JSONResponse(
        {
            "error": {
                "code": "replay_upstream_unavailable",
                "message": "The replay chronicle is temporarily unavailable.",
            }
        },
        status_code=503,
    )


def _iter_jsonl(file_path: str) -> Iterator[dict[str, Any]]:
    with Path(file_path).open(encoding="utf-8", errors="replace") as source:
        for line in source:
            try:
                value = json.loads(line)
            except (ValueError, TypeError):
                continue
            if (
                not isinstance(value, dict)
                or not isinstance(value.get("id"), int)
                or isinstance(value.get("id"), bool)
                or value["id"] <= 0
                or not isinstance(value.get("type"), str)
                or not value["type"].strip()
            ):
                continue
            yield value


def _fetch_from_file(
    file_path: str,
    citizen: str | None,
    type_: str | None,
    limit: int,
) -> list[dict]:
    newest: deque[dict[str, Any]] = deque(maxlen=max(1, min(limit, 1000)))
    for row in _iter_jsonl(file_path):
        if citizen and row.get("citizen") != citizen:
            continue
        if type_ and row.get("type") != type_:
            continue
        newest.append(row)
    return list(reversed(newest))


async def fetch_events(
    citizen: str | None = None,
    type_: str | None = None,
    limit: int = 100,
) -> list[dict]:
    if ECO_REPLAY_FILE:
        try:
            return _fetch_from_file(ECO_REPLAY_FILE, citizen, type_, limit)
        except OSError as error:
            raise ReplayUpstreamUnavailableError from error

    if ECO_REPLAY_UPSTREAM_URL:
        params: dict[str, str | int] = {"limit": limit}
        if citizen:
            params["citizen"] = citizen
        if type_:
            params["type"] = type_
        headers = {"X-API-Key": UPSTREAM_API_KEY} if UPSTREAM_API_KEY else {}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(ECO_REPLAY_UPSTREAM_URL, params=params, headers=headers)
                resp.raise_for_status()
                payload = resp.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
                raise ValueError("replay events response has no events list")
            return payload["events"]
        except (httpx.HTTPError, TypeError, ValueError) as error:
            raise ReplayUpstreamUnavailableError from error

    rows = _MOCK_EVENTS
    if citizen:
        rows = [r for r in rows if r["citizen"] == citizen]
    if type_:
        rows = [r for r in rows if r["type"] == type_]
    return rows[:limit]


def _stats_from_file(file_path: str) -> dict:
    return {"ready": True, "total": sum(1 for _ in _iter_jsonl(file_path))}


async def fetch_stats() -> dict:
    """Mirror the mod's `/api/v1/events/stats`: `{ ready, total }`."""
    if ECO_REPLAY_FILE:
        try:
            return _stats_from_file(ECO_REPLAY_FILE)
        except OSError as error:
            raise ReplayUpstreamUnavailableError from error

    if ECO_REPLAY_UPSTREAM_URL:
        headers = {"X-API-Key": UPSTREAM_API_KEY} if UPSTREAM_API_KEY else {}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{ECO_REPLAY_UPSTREAM_URL}/stats", headers=headers)
                resp.raise_for_status()
                payload = resp.json()
            if (
                not isinstance(payload, dict)
                or not isinstance(payload.get("ready"), bool)
                or not isinstance(payload.get("total"), int)
                or isinstance(payload["total"], bool)
            ):
                raise ValueError("replay stats response is malformed")
            return payload
        except (httpx.HTTPError, TypeError, ValueError) as error:
            raise ReplayUpstreamUnavailableError from error

    return {"ready": True, "total": len(_MOCK_EVENTS)}


@app.get("/v1/meta")
def api_meta() -> JSONResponse:
    """Whether the data below is the canned mock set (no JSONL / upstream set)."""
    return JSONResponse({"mockData": using_mock()})


@app.get("/v1/events")
async def api_events(
    citizen: str | None = None,
    type_: str | None = Query(default=None, alias="type"),
    limit: int = Query(default=100, ge=1, le=1000),
) -> JSONResponse:
    """JSON mirror of the upstream mod endpoint, with mock fallback."""
    try:
        events = await fetch_events(citizen=citizen, type_=type_, limit=limit)
    except ReplayUpstreamUnavailableError:
        return _unavailable_response()
    return JSONResponse({"events": events, "count": len(events)})


@app.get("/v1/events/stats")
async def api_events_stats() -> JSONResponse:
    """JSON mirror of the upstream mod `/stats` endpoint, with mock fallback."""
    try:
        return JSONResponse(await fetch_stats())
    except ReplayUpstreamUnavailableError:
        return _unavailable_response()
