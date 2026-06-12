"""FastAPI app for eco-replay.

Lists recorded player actions written by the C# Eco mod.

Two read paths, in priority order:

1. `ECO_REPLAY_DB` env var pointing at the mod's SQLite file
   (e.g. `/home/kai/Steam/steamapps/common/EcoServer/Storage/EcoReplay.db`).
   Opens in WAL read-only mode, so it's safe to run alongside the live
   server writes.
2. `UPSTREAM_URL` env var pointing at the mod's HTTP `/api/v1/events`
   endpoint. Eco's web server requires admin auth — set
   `UPSTREAM_API_KEY` to pass it through as `X-API-Key`.
3. Neither set: mock data, for local UI dev without an Eco server.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

ECO_REPLAY_DB = os.environ.get("ECO_REPLAY_DB")
UPSTREAM_URL = os.environ.get("UPSTREAM_URL")
UPSTREAM_API_KEY = os.environ.get("UPSTREAM_API_KEY")
USING_MOCK = ECO_REPLAY_DB is None and UPSTREAM_URL is None

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))
TEMPLATES.env.globals["using_mock_data"] = USING_MOCK

app = FastAPI(title="eco-replay", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


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

    if UPSTREAM_URL:
        params: dict[str, str | int] = {"limit": limit}
        if citizen:
            params["citizen"] = citizen
        if type_:
            params["type"] = type_
        headers = {"X-API-Key": UPSTREAM_API_KEY} if UPSTREAM_API_KEY else {}
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(UPSTREAM_URL, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json().get("events", [])

    rows = _MOCK_EVENTS
    if citizen:
        rows = [r for r in rows if r["citizen"] == citizen]
    if type_:
        rows = [r for r in rows if r["type"] == type_]
    return rows[:limit]


@app.get("/healthz")
def healthz() -> JSONResponse:
    return JSONResponse({"ok": True})


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    citizen: str | None = Query(default=None),
    type_: str | None = Query(default=None, alias="type"),
    limit: int = Query(default=100, ge=1, le=1000),
) -> HTMLResponse:
    events = await fetch_events(citizen=citizen, type_=type_, limit=limit)
    return TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {"events": events, "citizen": citizen, "type": type_, "limit": limit},
    )


@app.get("/api/v1/events")
async def api_events(
    citizen: str | None = None,
    type_: str | None = Query(default=None, alias="type"),
    limit: int = 100,
) -> JSONResponse:
    """JSON mirror of the upstream mod endpoint, with mock fallback."""
    events = await fetch_events(citizen=citizen, type_=type_, limit=limit)
    return JSONResponse({"events": events, "count": len(events)})
