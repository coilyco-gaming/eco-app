"""Fixture server: replay a captured snapshot as if it were the eco server.

Lookup order for an incoming GET:

1. Exact path + canonicalized query match.
2. Significant-param match (manifest.SIGNIFICANT_PARAMS) - so a request for
   `/datasets/get?dataset=X&dayEnd=<any>` hits the captured series for X no
   matter what day window the app computed.
3. Path-only match when the snapshot holds exactly one entry for the path -
   covers endpoints like `/api/v1/events` where the capture pinned a limit
   param the app may vary.
4. 404 with a JSON body naming the miss, so a gap in the capture list shows
   up loudly in the dev loop instead of as silent empty data.

Auth is ignored on purpose: the snapshot already dropped anything the admin
key gated, and the fixture binds to localhost.
"""

from __future__ import annotations

from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from eco_snapshot.manifest import Entry, Manifest, request_key, resource_key


def _indexes(
    manifest: Manifest,
) -> tuple[dict[str, Entry], dict[str, Entry], dict[str, list[Entry]]]:
    exact: dict[str, Entry] = {}
    by_resource: dict[str, Entry] = {}
    by_path: dict[str, list[Entry]] = {}
    for entry in manifest.entries:
        exact[entry.key] = entry
        rkey = resource_key(entry.path, entry.query)
        if rkey is not None:
            by_resource[rkey] = entry
        by_path.setdefault(entry.path, []).append(entry)
    return exact, by_resource, by_path


def build_app(snapshot_dir: Path) -> Starlette:
    manifest = Manifest.load(snapshot_dir)
    exact, by_resource, by_path = _indexes(manifest)

    def _lookup(path: str, query: str) -> Entry | None:
        entry = exact.get(request_key(path, query))
        if entry is not None:
            return entry
        rkey = resource_key(path, query)
        if rkey is not None and rkey in by_resource:
            return by_resource[rkey]
        candidates = by_path.get(path, [])
        if len(candidates) == 1:
            return candidates[0]
        return None

    async def replay(request: Request) -> Response:
        path = request.url.path
        query = request.url.query
        entry = _lookup(path, query)
        if entry is None:
            return JSONResponse(
                {"error": "not in snapshot", "path": path, "query": query},
                status_code=404,
            )
        body = (snapshot_dir / entry.file).read_bytes()
        return Response(content=body, media_type=entry.content_type)

    async def meta(request: Request) -> Response:
        return JSONResponse(
            {
                "captured_at": manifest.captured_at,
                "base_url": manifest.base_url,
                "day_end": manifest.day_end,
                "entries": len(manifest.entries),
                "failures": manifest.failures,
            }
        )

    return Starlette(
        routes=[
            Route("/_snapshot", meta),
            Route("/{rest:path}", replay),
        ]
    )
