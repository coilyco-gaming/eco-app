"""Capture every upstream eco-server response into a snapshot directory.

The endpoint list is the union of everything the app consumes (see
docs/datasets/README.md for the survey): the public /info card, the dataset
catalog and every series in it, every action exporter CSV, the species
exporter, civics/elections/laws, map dimensions + world-layer rasters, and
the mod surfaces (jobs skills/citizens, stores, replay events). Discovery is
data-driven where the server offers a catalog (flatlist, specieslist), so a
new dataset next cycle is captured without a code change.

Responses are stored byte-for-byte and indexed in manifest.json; failures
are recorded there too, never silently skipped.
"""

from __future__ import annotations

import asyncio
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from eco_snapshot.manifest import RESPONSES_DIR, Entry, Manifest, canonical_query

REQUEST_TIMEOUT_SECONDS = 30.0
CONCURRENCY = 8

QueryPairs = list[tuple[str, str]]

# Endpoints captured unconditionally. Catalog-driven fan-outs (series,
# actions, species) are appended at capture time.
STATIC_ENDPOINTS: list[tuple[str, QueryPairs]] = [
    ("/info", []),
    ("/datasets/flatlist", []),
    ("/api/v1/users", []),
    ("/api/v1/laws", [("byStates", "Active")]),
    ("/api/v1/elections", []),
    ("/api/v1/elections/titles", []),
    ("/api/v1/currency-holdings", []),
    ("/api/v1/worldlayers/layers", []),
    ("/api/v1/map/dimension", []),
    ("/api/v1/map/property", []),
    ("/api/v1/climate-settings", []),
    ("/api/v1/exporter/specieslist", []),
    ("/api/v1/skills", []),
    ("/api/v1/citizens", []),
    ("/api/v1/stores", []),
    ("/api/v1/events/stats", []),
    ("/Layers/WorldPreview.gif", []),
    ("/Layers/Pollution.gif", []),
]

REPLAY_PAGE_SIZE = 1000

_EXT_BY_TYPE = {
    "application/json": ".json",
    "text/csv": ".csv",
    "text/plain": ".txt",
    "image/gif": ".gif",
}


def _ext_for(content_type: str) -> str:
    return _EXT_BY_TYPE.get(content_type.split(";")[0].strip().lower(), ".bin")


def _slug(path: str, query: str) -> str:
    raw = f"{path}-{query}" if query else path
    return re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-")[:80]


def _day_end(info: dict[str, Any]) -> int:
    days = info.get("DaysRunning") or info.get("TimeSinceStart") or 1
    try:
        return max(1, math.ceil(float(days)))
    except (TypeError, ValueError):
        return 1


async def _fetch_json(
    client: httpx.AsyncClient, base: str, path: str, headers: dict[str, str]
) -> Any:
    r = await client.get(f"{base}{path}", headers=headers)
    r.raise_for_status()
    return r.json()


def _catalog_endpoints(flatlist: Any, day_end: int) -> list[tuple[str, QueryPairs]]:
    """Fan the dataset catalog out into one request per series / action."""
    out: list[tuple[str, QueryPairs]] = []
    if not isinstance(flatlist, list):
        return out
    for ds in flatlist:
        if not isinstance(ds, dict) or not ds.get("Name"):
            continue
        name = str(ds["Name"])
        if ds.get("IsAction"):
            out.append(("/api/v1/exporter/actions", [("actionName", name)]))
        else:
            out.append(
                (
                    "/datasets/get",
                    [("dataset", name), ("dayStart", "0"), ("dayEnd", str(day_end))],
                )
            )
    return out


def _species_endpoints(specieslist: str) -> list[tuple[str, QueryPairs]]:
    """specieslist is newline-delimited CamelCase species ids."""
    out: list[tuple[str, QueryPairs]] = []
    for line in specieslist.splitlines():
        species_id = line.strip()
        if species_id:
            out.append(("/api/v1/exporter/species", [("speciesName", species_id)]))
    return out


def _worldlayer_endpoints(catalog: Any) -> list[tuple[str, QueryPairs]]:
    """Fan the worldlayer catalog out into one raster request per layer.

    The map uses ``/Layers/<LayerName>.gif`` for hover highlights, and custom
    worlds can add layers beyond the built-in biome names.  The catalog is the
    authority here so a capture includes every raster the server advertises.
    """
    if not isinstance(catalog, list):
        return []

    out: list[tuple[str, QueryPairs]] = []
    for category in catalog:
        if not isinstance(category, dict):
            continue
        layers = category.get("List")
        if not isinstance(layers, list):
            continue
        for layer in layers:
            if not isinstance(layer, dict):
                continue
            name = layer.get("LayerName")
            if isinstance(name, str) and name:
                out.append((f"/Layers/{name}.gif", []))
    return out


def _replay_events(payload: Any) -> list[dict[str, Any]] | None:
    """Read the replay mod's paged payload, accepting its legacy list shape."""
    events = payload.get("events") if isinstance(payload, dict) else payload
    if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
        return None
    return events


async def capture_snapshot(
    base_url: str,
    out_dir: Path,
    api_key: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> Manifest:
    """Pull every endpoint into `out_dir` and return the saved manifest."""
    base = base_url.rstrip("/")
    headers = {"X-API-Key": api_key} if api_key else {}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / RESPONSES_DIR).mkdir(exist_ok=True)

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)
    manifest = Manifest(captured_at=datetime.now(UTC).isoformat(), base_url=base)
    try:
        endpoints = list(STATIC_ENDPOINTS)

        # Catalog discovery first: /info supplies the day window, flatlist
        # and specieslist supply the fan-out lists. Each is best-effort -
        # a failure trims the fan-out but never aborts the capture.
        try:
            manifest.day_end = _day_end(await _fetch_json(client, base, "/info", headers))
        except (httpx.HTTPError, ValueError) as exc:
            manifest.day_end = 1
            manifest.failures.append({"path": "/info", "query": "", "reason": str(exc)})
        try:
            flatlist = await _fetch_json(client, base, "/datasets/flatlist", headers)
            endpoints += _catalog_endpoints(flatlist, manifest.day_end)
        except (httpx.HTTPError, ValueError) as exc:
            manifest.failures.append(
                {"path": "/datasets/flatlist", "query": "", "reason": f"fan-out skipped: {exc}"}
            )
        try:
            r = await client.get(f"{base}/api/v1/exporter/specieslist", headers=headers)
            r.raise_for_status()
            endpoints += _species_endpoints(r.text)
        except httpx.HTTPError as exc:
            manifest.failures.append(
                {
                    "path": "/api/v1/exporter/specieslist",
                    "query": "",
                    "reason": f"fan-out skipped: {exc}",
                }
            )
        try:
            worldlayers = await _fetch_json(client, base, "/api/v1/worldlayers/layers", headers)
            endpoints += _worldlayer_endpoints(worldlayers)
        except (httpx.HTTPError, ValueError) as exc:
            manifest.failures.append(
                {
                    "path": "/api/v1/worldlayers/layers",
                    "query": "",
                    "reason": f"fan-out skipped: {exc}",
                }
            )

        # Keep the explicitly requested preview/pollution layers and avoid
        # duplicate catalog entries when either one is also advertised.
        deduped: list[tuple[str, QueryPairs]] = []
        seen: set[tuple[str, str]] = set()
        for path, pairs in endpoints:
            key = (path, canonical_query(pairs))
            if key not in seen:
                seen.add(key)
                deduped.append((path, pairs))

        semaphore = asyncio.Semaphore(CONCURRENCY)

        async def pull(index: int, path: str, pairs: QueryPairs) -> httpx.Response | None:
            query = canonical_query(pairs)
            async with semaphore:
                try:
                    r = await client.get(f"{base}{path}", params=tuple(pairs), headers=headers)
                except httpx.HTTPError as exc:
                    manifest.failures.append({"path": path, "query": query, "reason": str(exc)})
                    return None
            if r.status_code != 200:
                manifest.failures.append(
                    {"path": path, "query": query, "reason": f"HTTP {r.status_code}"}
                )
                return None
            content_type = r.headers.get("content-type", "application/octet-stream")
            rel = f"{RESPONSES_DIR}/{index:04d}-{_slug(path, query)}{_ext_for(content_type)}"
            (out_dir / rel).write_bytes(r.content)
            manifest.entries.append(
                Entry(
                    path=path,
                    query=query,
                    file=rel,
                    status=r.status_code,
                    content_type=content_type,
                )
            )
            return r

        tasks = [pull(index, path, pairs) for index, (path, pairs) in enumerate(deduped, start=1)]
        await asyncio.gather(*tasks)

        # The replay mod returns newest-first pages.  ``beforeId`` is an
        # exclusive cursor, so advancing to the smallest id in each page
        # captures a complete event history without overlap.
        event_index = len(deduped)
        before_id: int | None = None
        while True:
            event_index += 1
            replay_pairs: QueryPairs = [("limit", str(REPLAY_PAGE_SIZE))]
            if before_id is not None:
                replay_pairs.append(("beforeId", str(before_id)))
            response = await pull(event_index, "/api/v1/events", replay_pairs)
            if response is None:
                break
            try:
                events = _replay_events(response.json())
            except ValueError:
                events = None
            if events is None:
                manifest.failures.append(
                    {
                        "path": "/api/v1/events",
                        "query": canonical_query(replay_pairs),
                        "reason": "pagination stopped: invalid events payload",
                    }
                )
                break
            if len(events) < REPLAY_PAGE_SIZE:
                break
            ids: list[int] = []
            for event in events:
                event_id = event.get("id")
                if isinstance(event_id, int):
                    ids.append(event_id)
            if not ids:
                manifest.failures.append(
                    {
                        "path": "/api/v1/events",
                        "query": canonical_query(replay_pairs),
                        "reason": "pagination stopped: full page has no integer ids",
                    }
                )
                break
            next_before_id = min(ids)
            if before_id is not None and next_before_id >= before_id:
                manifest.failures.append(
                    {
                        "path": "/api/v1/events",
                        "query": canonical_query(replay_pairs),
                        "reason": "pagination stopped: beforeId cursor did not advance",
                    }
                )
                break
            before_id = next_before_id
    finally:
        if owns_client:
            await client.aclose()

    manifest.entries.sort(key=lambda e: e.file)
    manifest.save(out_dir)
    return manifest
