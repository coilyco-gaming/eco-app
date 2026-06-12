"""FastAPI app for the jobs tracker (formerly eco-jobs-tracker).

Serves a Jinja2 + HTMX UI plus a JSON API, backed by the Eco mod's
`/api/v1/skills` endpoint (`UPSTREAM_URL`) with a mock-data fallback.

Runs mounted at `/jobs` inside eco_mcp_app's ASGI app (http_app.py) — the
fused eco-app service. Templates prefix every absolute URL with
`request.scope.root_path` so they work under the mount. The app remains a
valid standalone ASGI target for local dev (`uvicorn eco_spec_tracker.main:app`).

General server stats live on the SPA landing page at `/`; this page is
jobs-only and shares its visual language via static/theme.css.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from eco_mcp_app.telemetry import init_sentry
from eco_spec_tracker import mock_data, upstream
from eco_spec_tracker.livereload import DEBUG, LIVERELOAD_SCRIPT
from eco_spec_tracker.livereload import router as livereload_router

# Shared idempotent init from eco_mcp_app — in the fused process both
# entrypoints call it; whichever runs first wins, the rest are no-ops.
init_sentry()

# Allow coilysiren.me to embed this app in an iframe (eco-modding page) via
# frame-ancestors. Keep X-Frame-Options unset everywhere (app + ingress).
FRAME_ANCESTORS_CSP = "frame-ancestors 'self' https://www.coilysiren.me https://coilysiren.me"

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))

TEMPLATES.env.globals["livereload_script"] = LIVERELOAD_SCRIPT if DEBUG else ""
TEMPLATES.env.globals["using_mock_data"] = upstream.UPSTREAM_URL is None

app = FastAPI(title="eco-jobs-tracker", version="0.1.0")


@app.middleware("http")
async def add_frame_ancestors_csp(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = FRAME_ANCESTORS_CSP
    return response


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
if DEBUG:
    app.include_router(livereload_router)


@app.get("/healthz")
def healthz() -> JSONResponse:
    return JSONResponse({"ok": True})


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Homepage: all three content sections stacked."""
    rows = await upstream.fetch_rows()
    return TEMPLATES.TemplateResponse(
        request,
        "index.html",
        {
            "stats": mock_data.profession_stats(rows),
            "specialties": mock_data.specialties(rows),
            "players": mock_data.players(rows),
        },
    )


@app.get("/professions", response_class=HTMLResponse)
async def professions_page(request: Request) -> HTMLResponse:
    """Just the Professions section, no eco card."""
    rows = await upstream.fetch_rows()
    return TEMPLATES.TemplateResponse(
        request, "professions.html", {"stats": mock_data.profession_stats(rows)}
    )


@app.get("/specialties", response_class=HTMLResponse)
async def specialties_page(request: Request) -> HTMLResponse:
    """Just the Specialties section, no eco card."""
    rows = await upstream.fetch_rows()
    return TEMPLATES.TemplateResponse(
        request, "specialties.html", {"specialties": mock_data.specialties(rows)}
    )


@app.get("/players", response_class=HTMLResponse)
async def players_page(request: Request) -> HTMLResponse:
    """Just the Players section, no eco card."""
    rows = await upstream.fetch_rows()
    return TEMPLATES.TemplateResponse(request, "players.html", {"players": mock_data.players(rows)})


@app.get("/partials/profession/{name}", response_class=HTMLResponse)
async def partial_profession_detail(request: Request, name: str) -> HTMLResponse:
    """HTMX partial: expand a profession to see its players."""
    rows = await upstream.fetch_rows()
    stats = {s.profession: s for s in mock_data.profession_stats(rows)}
    stat = stats.get(name)
    if stat is None:
        return HTMLResponse(f"<p>Unknown profession: {name}</p>", status_code=404)
    return TEMPLATES.TemplateResponse(request, "_profession_detail.html", {"stat": stat})


# --- JSON API (machine-readable mirror of the live data) ---


@app.get("/api/v1/professions")
async def api_professions() -> JSONResponse:
    rows = await upstream.fetch_rows()
    stats = mock_data.profession_stats(rows)
    return JSONResponse(
        [
            {"profession": s.profession, "active": s.active, "total": s.total, "players": s.players}
            for s in stats
        ]
    )


@app.get("/api/v1/players")
async def api_players() -> JSONResponse:
    rows = await upstream.fetch_rows()
    return JSONResponse(
        [
            {
                "name": p.name,
                "active": p.active,
                "specialties": [
                    {"specialty": s.specialty, "level": s.level, "active": s.active}
                    for s in p.specialties
                ],
            }
            for p in mock_data.players(rows)
        ]
    )


@app.get("/api/v1/specialties")
async def api_specialties() -> JSONResponse:
    rows = await upstream.fetch_rows()
    return JSONResponse(
        [
            {
                "specialty": s.name,
                "profession": s.profession,
                "active": s.active,
                "total": s.total,
                "holders": [
                    {"player": h.player, "level": h.level, "active": h.active} for h in s.holders
                ],
            }
            for s in mock_data.specialties(rows)
        ]
    )
