"""JSON API for eco-replay (the "Kaihronicler" — a Chronicler mirror).

Lists recorded player actions written by the C# Eco replay mod. Mounted at
`/replay/api` inside eco_mcp_app's ASGI app (http_app.py), so the public paths
are `/replay/api/v1/*`, mirroring the jobs tracker's `/jobs/api` mount. The
browser UI is the React SPA's `/replay` route, which consumes this API (plus
`/v1/meta` for the mock-data banner) — there is no server-rendered HTML surface
here, per the repo's SPA-only rule (eco-app#38, DLT epic #37).

Three read paths, in priority order:

1. `ECO_REPLAY_DB` env var pointing at the mod's SQLite file
   (e.g. `/home/kai/Steam/steamapps/common/EcoServer/Storage/EcoReplay.db`).
   Opens in WAL read-only mode, so it's safe to run alongside the live
   server writes.
2. `ECO_REPLAY_UPSTREAM_URL` env var pointing at the mod's HTTP `/api/v1/events`
   endpoint. Eco's web server requires admin auth — set
   `UPSTREAM_API_KEY` to pass it through as `X-API-Key`.
3. Neither set: mock data, for local UI dev without an Eco server.
"""

from __future__ import annotations

import json
import os
import sqlite3

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from eco_mcp_app.telemetry import init_telemetry

ECO_REPLAY_DB = os.environ.get("ECO_REPLAY_DB")
ECO_REPLAY_UPSTREAM_URL = os.environ.get("ECO_REPLAY_UPSTREAM_URL")
UPSTREAM_API_KEY = os.environ.get("UPSTREAM_API_KEY")

# Shared idempotent init from eco_mcp_app — in the fused process every
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
    """Whether replay has neither its database nor its dedicated HTTP source."""
    return ECO_REPLAY_DB is None and ECO_REPLAY_UPSTREAM_URL is None


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


def _fetch_from_db(
    db_path: str,
    citizen: str | None,
    type_: str | None,
    limit: int,
) -> list[dict]:
    # Read-only open with URI mode so concurrent writes from the mod
    # are safe. WAL mode means readers don't block writers.
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        sql = (
            "SELECT id, unix_time, game_time, action_type, citizen, body_json FROM events WHERE 1=1"
        )
        params: list[object] = []
        if citizen:
            sql += " AND citizen = ?"
            params.append(citizen)
        if type_:
            sql += " AND action_type = ?"
            params.append(type_)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(limit, 1000)))
        return [
            {
                "id": r[0],
                "unixTime": r[1],
                "gameTime": r[2],
                "type": r[3],
                "citizen": r[4],
                "body": r[5],
            }
            for r in conn.execute(sql, params).fetchall()
        ]
    finally:
        conn.close()


async def fetch_events(
    citizen: str | None = None,
    type_: str | None = None,
    limit: int = 100,
) -> list[dict]:
    if ECO_REPLAY_DB:
        return _fetch_from_db(ECO_REPLAY_DB, citizen, type_, limit)

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


def _stats_from_db(db_path: str) -> dict:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        total = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return {"ready": True, "total": total}
    finally:
        conn.close()


async def fetch_stats() -> dict:
    """Mirror the mod's `/api/v1/events/stats`: `{ ready, total }`."""
    if ECO_REPLAY_DB:
        return _stats_from_db(ECO_REPLAY_DB)

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
    """Whether the data below is the canned mock set (no DB / upstream set)."""
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
