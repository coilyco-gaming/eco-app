"""ASGI wrapper that exposes the MCP server over Streamable-HTTP.

Used for the homelab deploy (eco-mcp.coilysiren.me). Claude Desktop still
talks to this process over stdio via `__main__.py`; HTTP is for hosts that
connect to an MCP server by URL.

Built on Starlette (not plain FastAPI) so `Mount("/mcp", ...)` cleanly
matches both `/mcp` and `/mcp/` without the trailing-slash redirect FastAPI
inserts by default. Middleware normalizes bare-path `/mcp` to the mount path
so both forms work.

Also exposes the `/preview*.json` data plane the React SPA consumes
(`/preview.json`, `/preview-map.json`, `/preview/<tool>.json`). The old HTML
`/preview` card pages were removed: product UX lives in the SPA (`frontend/`),
and the Jinja cards survive only on the MCP `_meta.ui` fragment for in-chat
hosts.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import httpx
import mcp.types as mt
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
)
from starlette.routing import BaseRoute, Mount, Route
from starlette.staticfiles import StaticFiles

from .admin import build_admin_server
from .livereload import DEBUG, livereload_route
from .map import build_map_payload, fetch_map_bundle
from .server import (
    HTMX_PREFIX,
    build_server,
    fetch_eco_info,
    redact,
    to_payload,
)
from .telemetry import init_sentry

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send


class FrameAncestorsCSP:
    """ASGI middleware — allow coilysiren.me to iframe-embed this site.

    Lived on the jobs tracker app when /jobs was its own Jinja surface (the
    eco-modding page on the personal site embeds it); now that every page is
    the SPA, the header applies site-wide. Keep X-Frame-Options unset
    everywhere (app + ingress).
    """

    CSP = "frame-ancestors 'self' https://www.coilysiren.me https://coilysiren.me"

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_csp(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Content-Security-Policy"] = self.CSP
            await send(message)

        await self.app(scope, receive, send_with_csp)


class NormalizeMcpPath:
    """ASGI middleware — rewrites scope.path `/mcp` → `/mcp/` before routing.

    Starlette's `Mount("/mcp", ...)` matches `/mcp/` and `/mcp/anything` but
    not bare `/mcp`. Some MCP clients POST straight to `/mcp` and don't follow
    redirects. Normalizing here is less invasive than two overlapping routes.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") == "/mcp":
            scope = {**scope, "path": "/mcp/", "raw_path": b"/mcp/"}
        await self.app(scope, receive, send)


class NormalizeAdminPath:
    """ASGI middleware - rewrites bare `/admin` → `/admin/` before routing.

    Same trailing-slash fix as `NormalizeMcpPath`, for the feature-flagged
    privileged MCP mount. Only added to the stack when `ECO_ADMIN_ENABLED` is
    set, so the public app's routing is untouched when the flag is off.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path") == "/admin":
            scope = {**scope, "path": "/admin/", "raw_path": b"/admin/"}
        await self.app(scope, receive, send)


def _env_flag(name: str) -> bool:
    """True when env var `name` is set to a truthy string (1/true/yes/on)."""
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


# Feature flag: the privileged /admin MCP is off unless explicitly enabled, so
# the public eco-mcp.coilysiren.me deploy never exposes on-disk state tools.
ADMIN_ENABLED_ENV = "ECO_ADMIN_ENABLED"


def create_app() -> Starlette:
    init_sentry()
    mcp_server = build_server()
    # stateless=True: every request gets a fresh transport. Fits the tool shape
    # — each call is a one-shot /info fetch, no long-lived session state.
    session_manager = StreamableHTTPSessionManager(app=mcp_server, stateless=True)

    # The privileged /admin MCP (on-disk state tools) is built and mounted only
    # when ECO_ADMIN_ENABLED is set. Its session manager is entered in the same
    # lifespan so both transports share one process lifetime.
    admin_enabled = _env_flag(ADMIN_ENABLED_ENV)
    admin_session_manager = (
        StreamableHTTPSessionManager(app=build_admin_server(), stateless=True)
        if admin_enabled
        else None
    )

    @asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(session_manager.run())
            if admin_session_manager is not None:
                await stack.enter_async_context(admin_session_manager.run())
            yield

    call_tool_handler = mcp_server.request_handlers[mt.CallToolRequest]
    list_tools_handler = mcp_server.request_handlers[mt.ListToolsRequest]

    async def _list_tools() -> mt.ListToolsResult:
        result = await list_tools_handler(mt.ListToolsRequest(method="tools/list"))
        return cast(mt.ListToolsResult, result.root)

    # The built React SPA (frontend/dist, baked into the Docker image) owns
    # the root and every client route. A checkout without a frontend build
    # has no HTML surface at all (the dev `/preview` cards were removed) — it
    # serves the JSON/MCP APIs only and points the visitor at the build verb.
    # Path is cwd-relative because the image WORKDIR and local `make http`
    # both run from the repo root; FRONTEND_DIST overrides for anything else.
    frontend_dist = Path(os.getenv("FRONTEND_DIST", "frontend/dist"))
    frontend_index = frontend_dist / "index.html"

    no_build_msg = (
        "Frontend not built. Run `ward exec frontend-build` (or `ward exec "
        "frontend-dev` for hot reload). JSON APIs are live at /preview.json, "
        "/preview/<tool>.json, /info, and /jobs/api/v1/*."
    )

    async def root(_: Request) -> Response:
        if frontend_index.is_file():
            return FileResponse(frontend_index)
        return PlainTextResponse(no_build_msg, status_code=404)

    async def spa_fallback(request: Request) -> Response:
        """Catch-all so the SPA's client-side routes survive a hard refresh.

        Registered last: every API route and mount above wins first. Real
        files in dist (favicon, robots.txt) serve as themselves; anything
        else gets index.html and the router takes it from there. Without a
        frontend build there's no HTML surface, so return the build hint.
        """
        if not frontend_index.is_file():
            return PlainTextResponse(no_build_msg, status_code=404)
        candidate = (frontend_dist / request.path_params["path"]).resolve()
        if candidate.is_file() and candidate.is_relative_to(frontend_dist.resolve()):
            return FileResponse(candidate)
        return FileResponse(frontend_index)

    async def service_info(_: Request) -> JSONResponse:
        tools_result = await _list_tools()
        names = sorted(t.name for t in tools_result.tools)
        return JSONResponse(
            {
                "service": "eco-app",
                "mcp": "/mcp/",
                "jobs": "/jobs",
                "jobsApi": "/jobs/api/v1",
                "replay": "/replay",
                "replayApi": "/replay/api/v1",
                "health": "/healthz",
                "previewJson": "/preview.json",
                "previewMapJson": "/preview-map.json",
                "previewToolsJson": [f"/preview/{name}.json" for name in names],
            }
        )

    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    # The `/preview*.json` family is the SPA's data plane: the React pages
    # (/server, /economy, /crafting, /climate) fetch these. The HTML `/preview`
    # cards that used to share these handlers were removed — product UX lives
    # in the SPA, the Jinja cards live only on MCP `_meta.ui` for in-chat hosts.
    async def preview_json(request: Request) -> JSONResponse:
        server_arg = request.query_params.get("server")
        try:
            raw = await fetch_eco_info(server_arg)
        except httpx.HTTPError as e:
            return JSONResponse({"error": str(e)}, status_code=502)
        info = redact(raw)
        info["_fetchedAtISO"] = datetime.now(UTC).isoformat()
        return JSONResponse(to_payload(info))

    async def preview_map_json(request: Request) -> JSONResponse:
        server_arg = request.query_params.get("server")
        try:
            bundle = await fetch_map_bundle(server_arg)
        except httpx.HTTPError as e:
            return JSONResponse({"error": str(e)}, status_code=502)
        return JSONResponse(build_map_payload(bundle))

    async def preview_currency_json(request: Request) -> JSONResponse:
        """`/preview/currency.json` — the SPA's `/trade` route data plane.

        Dispatches `get_eco_currency` and returns its JSON block. A dedicated
        route (rather than the generic `/preview/<tool>.json`) so the SPA can
        hit the short, stable `/preview/currency.json` path the epic asked for,
        and so `?server=` / `?currency=` pass straight through as tool args.
        """
        args = {k: v for k, v in request.query_params.items() if k in ("server", "currency")}
        req = mt.CallToolRequest(
            method="tools/call",
            params=mt.CallToolRequestParams(name="get_eco_currency", arguments=args),
        )
        try:
            result = await call_tool_handler(req)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        payload = _extract_json_block(cast(mt.CallToolResult, result.root))
        if payload is None:
            return JSONResponse({"error": "no JSON block from get_eco_currency"}, status_code=502)
        return JSONResponse(payload)

    async def preview_market_json(request: Request) -> JSONResponse:
        """`/preview/market.json` — the SPA's `/trade` price-intelligence plane.

        Dispatches `get_eco_market` and returns its JSON block. A dedicated
        route (rather than the generic `/preview/<tool>.json`) so the SPA hits
        the short, stable path the epic asked for, and so `?server=` / `?item=`
        / `?currency=` pass straight through as tool args.
        """
        args = {
            k: v for k, v in request.query_params.items() if k in ("server", "item", "currency")
        }
        req = mt.CallToolRequest(
            method="tools/call",
            params=mt.CallToolRequestParams(name="get_eco_market", arguments=args),
        )
        try:
            result = await call_tool_handler(req)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        payload = _extract_json_block(cast(mt.CallToolResult, result.root))
        if payload is None:
            return JSONResponse({"error": "no JSON block from get_eco_market"}, status_code=502)
        return JSONResponse(payload)

    async def preview_stores_json(request: Request) -> JSONResponse:
        """`/preview/stores.json` — the SPA's store/trader directory data plane.

        Dispatches `get_eco_stores` and returns its JSON block. A dedicated
        route (rather than the generic `/preview/<tool>.json`) so the SPA can
        hit the short, stable `/preview/stores.json` path the epic asked for,
        with `?server=` passing straight through as the tool arg (eco-app#50).
        """
        args = {k: v for k, v in request.query_params.items() if k in ("server",)}
        req = mt.CallToolRequest(
            method="tools/call",
            params=mt.CallToolRequestParams(name="get_eco_stores", arguments=args),
        )
        try:
            result = await call_tool_handler(req)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        payload = _extract_json_block(cast(mt.CallToolResult, result.root))
        if payload is None:
            return JSONResponse({"error": "no JSON block from get_eco_stores"}, status_code=502)
        return JSONResponse(payload)

    async def preview_logistics_json(request: Request) -> JSONResponse:
        """`/preview/logistics.json` — the SPA's trade-logistics data plane.

        Dispatches `find_eco_trade` and returns its JSON block. A dedicated route
        (rather than the generic `/preview/<tool>.json`) so the SPA hits the
        short, stable path the epic asked for, with `?server=` / `?item=` /
        `?currency=` passing straight through as tool args (eco-app#51).
        """
        args = {
            k: v for k, v in request.query_params.items() if k in ("server", "item", "currency")
        }
        req = mt.CallToolRequest(
            method="tools/call",
            params=mt.CallToolRequestParams(name="find_eco_trade", arguments=args),
        )
        try:
            result = await call_tool_handler(req)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        payload = _extract_json_block(cast(mt.CallToolResult, result.root))
        if payload is None:
            return JSONResponse({"error": "no JSON block from find_eco_trade"}, status_code=502)
        return JSONResponse(payload)

    async def preview_progression_json(request: Request) -> JSONResponse:
        """`/preview/progression.json` — the SPA's skills-history data plane.

        Dispatches `get_eco_progression` and returns its JSON block. A dedicated
        route (rather than the generic `/preview/<tool>.json`) so the SPA can hit
        the short, stable `/preview/progression.json` path the issue asked for,
        with `?server=` passing straight through as the tool arg (eco-app#64).
        """
        args = {k: v for k, v in request.query_params.items() if k in ("server",)}
        req = mt.CallToolRequest(
            method="tools/call",
            params=mt.CallToolRequestParams(name="get_eco_progression", arguments=args),
        )
        try:
            result = await call_tool_handler(req)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        payload = _extract_json_block(cast(mt.CallToolResult, result.root))
        if payload is None:
            return JSONResponse(
                {"error": "no JSON block from get_eco_progression"}, status_code=502
            )
        return JSONResponse(payload)

    async def preview_social_json(request: Request) -> JSONResponse:
        """`/preview/social.json` — the SPA's `/social` route data plane.

        Dispatches `get_eco_social` and returns its JSON block. This is a
        **public** path, so it never forwards `reveal_names`: the surface is
        always redacted (handles + name-scrubbed message bodies), regardless of
        any server-side names gate. A dedicated route (not the generic
        `/preview/<tool>.json`) so `?server=` passes straight through and the
        redaction posture is pinned here rather than left to a query param
        (eco-app#63).
        """
        args = {k: v for k, v in request.query_params.items() if k in ("server",)}
        req = mt.CallToolRequest(
            method="tools/call",
            params=mt.CallToolRequestParams(name="get_eco_social", arguments=args),
        )
        try:
            result = await call_tool_handler(req)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        payload = _extract_json_block(cast(mt.CallToolResult, result.root))
        if payload is None:
            return JSONResponse({"error": "no JSON block from get_eco_social"}, status_code=502)
        return JSONResponse(payload)

    async def preview_world_json(request: Request) -> JSONResponse:
        """`/preview/world.json` — the SPA's `/world` route data plane.

        Dispatches `get_eco_world` and returns its JSON block. A dedicated route
        (rather than the generic `/preview/<tool>.json`) so the SPA hits the
        short, stable path the issue asked for, with `?server=` passing straight
        through as the tool arg (eco-app#62).
        """
        args = {k: v for k, v in request.query_params.items() if k in ("server",)}
        req = mt.CallToolRequest(
            method="tools/call",
            params=mt.CallToolRequestParams(name="get_eco_world", arguments=args),
        )
        try:
            result = await call_tool_handler(req)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        payload = _extract_json_block(cast(mt.CallToolResult, result.root))
        if payload is None:
            return JSONResponse({"error": "no JSON block from get_eco_world"}, status_code=502)
        return JSONResponse(payload)

    async def preview_watchers_json(request: Request) -> JSONResponse:
        """`/preview/watchers.json` — the SPA's trade-watcher data plane.

        Dispatches `eco_trade_watchers` with `action=evaluate` in *peek* mode
        (`advance=false`), so loading the `/trades` page shows each watcher's
        current matching state without consuming its feed mark — only the MCP
        `evaluate` verb (advance defaulting true) advances the last-seen marks.
        A dedicated route (not the generic `/preview/<tool>.json`) so the bool
        arg is a real boolean, not the truthy string a query param would be.
        """
        args: dict[str, Any] = {"action": "evaluate", "advance": False}
        if "server" in request.query_params:
            args["server"] = request.query_params["server"]
        req = mt.CallToolRequest(
            method="tools/call",
            params=mt.CallToolRequestParams(name="eco_trade_watchers", arguments=args),
        )
        try:
            result = await call_tool_handler(req)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        payload = _extract_json_block(cast(mt.CallToolResult, result.root))
        if payload is None:
            return JSONResponse({"error": "no JSON block from eco_trade_watchers"}, status_code=502)
        return JSONResponse(payload)

    def _extract_json_block(call_result: mt.CallToolResult) -> Any:
        # Each tool emits markdown + JSON TextContent blocks (see
        # server.call_tool). Find the JSON one by skipping any HTMX-prefixed
        # block and trying to parse each remaining text block; first that
        # parses wins.
        for block in call_result.content:
            text = getattr(block, "text", "") or ""
            if text.startswith(HTMX_PREFIX):
                continue
            try:
                return json.loads(text)
            except (ValueError, TypeError):
                continue
        return None

    async def preview_tool(request: Request) -> JSONResponse:
        """Dispatch any MCP tool by name and return its JSON content block.

        The SPA consumes `/preview/<tool>.json?<args>` — query-string args pass
        straight through as the tool's `arguments`, so
        `/preview/get_eco_species.json?name=Bison` works. The `.json` suffix is
        required; the HTML card variant was removed (the in-chat card now lives
        only on the MCP `_meta.ui` fragment, and the web UI is the SPA).
        """
        raw_name = request.path_params["tool"]
        if not raw_name.endswith(".json"):
            return JSONResponse(
                {"error": "only the .json data endpoint is served (e.g. /preview/<tool>.json)"},
                status_code=404,
            )
        tool_name = raw_name[: -len(".json")]
        args = dict(request.query_params)
        req = mt.CallToolRequest(
            method="tools/call",
            params=mt.CallToolRequestParams(name=tool_name, arguments=args),
        )
        try:
            result = await call_tool_handler(req)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        call_result = cast(mt.CallToolResult, result.root)
        payload = _extract_json_block(call_result)
        if payload is None:
            return JSONResponse(
                {"error": f"tool '{tool_name}' did not return a JSON content block"},
                status_code=404,
            )
        return JSONResponse(payload)

    async def handle_mcp(scope: Scope, receive: Receive, send: Send) -> None:
        await session_manager.handle_request(scope, receive, send)

    async def handle_admin_mcp(scope: Scope, receive: Receive, send: Send) -> None:
        assert admin_session_manager is not None  # only mounted when enabled
        await admin_session_manager.handle_request(scope, receive, send)

    # The jobs JSON API (eco_spec_tracker) and the replay JSON API (eco_replay,
    # the Chronicler mirror) are self-contained FastAPI apps mounted under
    # /jobs/api and /replay/api. Their browser UIs are the SPA's /jobs and
    # /replay routes, served by the catch-all below. Imported here (not module
    # top) so the mounts only exist on the ASGI path, keeping stdio lean.
    from eco_replay.main import app as replay_app
    from eco_spec_tracker.main import app as jobs_app

    routes: list[BaseRoute] = [
        Route("/", root, methods=["GET"]),
        Route("/info", service_info, methods=["GET"]),
        Route("/healthz", healthz, methods=["GET"]),
        Route("/preview.json", preview_json, methods=["GET"]),
        Route("/preview-map.json", preview_map_json, methods=["GET"]),
        Route("/preview/currency.json", preview_currency_json, methods=["GET"]),
        Route("/preview/market.json", preview_market_json, methods=["GET"]),
        Route("/preview/stores.json", preview_stores_json, methods=["GET"]),
        Route("/preview/logistics.json", preview_logistics_json, methods=["GET"]),
        Route("/preview/progression.json", preview_progression_json, methods=["GET"]),
        Route("/preview/social.json", preview_social_json, methods=["GET"]),
        Route("/preview/world.json", preview_world_json, methods=["GET"]),
        Route("/preview/watchers.json", preview_watchers_json, methods=["GET"]),
        Route("/preview/{tool}", preview_tool, methods=["GET"]),
        Mount("/mcp", app=handle_mcp),
        Mount("/jobs/api", app=jobs_app),
        Mount("/replay/api", app=replay_app),
    ]
    if admin_enabled:
        routes.append(Mount("/admin", app=handle_admin_mcp))
    if (frontend_dist / "assets").is_dir():
        routes.append(Mount("/assets", app=StaticFiles(directory=frontend_dist / "assets")))
    if DEBUG:
        routes.append(livereload_route)
    routes.append(Route("/{path:path}", spa_fallback, methods=["GET"]))
    inner = Starlette(lifespan=lifespan, routes=routes)
    inner.add_middleware(NormalizeMcpPath)
    if admin_enabled:
        inner.add_middleware(NormalizeAdminPath)
    inner.add_middleware(FrameAncestorsCSP)
    return inner


app = create_app()
