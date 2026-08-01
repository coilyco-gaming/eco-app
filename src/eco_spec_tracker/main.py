"""JSON API for the jobs tracker (formerly eco-jobs-tracker).

Row-shaping over the Eco mod's `/api/v1/skills` endpoint (`UPSTREAM_URL`)
with a mock-data fallback. Mounted at `/jobs/api` inside eco_mcp_app's ASGI
app (http_app.py), so the public paths stay `/jobs/api/v1/*` - unchanged
from the era when this package also served the jobs HTML. The browser UI is
the React SPA's `/jobs` route, which consumes this API (plus `/v1/meta` for
the mock-data banner).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from eco_mcp_app.telemetry import init_telemetry
from eco_spec_tracker import mock_data, upstream

# Shared idempotent init from eco_mcp_app — in the fused process both
# entrypoints call it; whichever runs first wins, the rest are no-ops.
init_telemetry()

app = FastAPI(title="eco-jobs-api", version="0.2.0")


@app.get("/v1/meta")
def api_meta() -> JSONResponse:
    """Whether the data below is the canned mock set (UPSTREAM_URL unset)."""
    return JSONResponse({"mockData": upstream.UPSTREAM_URL is None})


@app.get("/v1/professions")
async def api_professions() -> JSONResponse:
    rows = await upstream.fetch_rows()
    stats = mock_data.profession_stats(rows)
    return JSONResponse(
        [
            {
                "profession": s.profession,
                "active": s.active,
                "covered": s.covered,
                "total": s.total,
                "players": s.players,
            }
            for s in stats
        ]
    )


@app.get("/v1/players")
async def api_players() -> JSONResponse:
    rows = await upstream.fetch_rows()
    return JSONResponse(
        [
            {
                "name": p.name,
                "active": p.active,
                "roles": p.roles,
                "specialties": [
                    {"specialty": s.specialty, "level": s.level, "active": s.active}
                    for s in p.specialties
                ],
            }
            for p in mock_data.players(rows)
        ]
    )


@app.get("/v1/specialties")
async def api_specialties() -> JSONResponse:
    rows = await upstream.fetch_rows()
    return JSONResponse(
        [
            {
                "specialty": s.name,
                "profession": s.profession,
                "active": s.active,
                "covered": s.covered,
                "total": s.total,
                "holders": [
                    {"player": h.player, "level": h.level, "active": h.active, "roles": h.roles}
                    for h in s.holders
                ],
            }
            for s in mock_data.specialties(rows)
        ]
    )
