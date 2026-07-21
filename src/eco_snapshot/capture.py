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
    ("/api/v1/events", [("limit", "1000")]),
    ("/api/v1/events/stats", []),
    ("/Layers/WorldPreview.gif", []),
    ("/Layers/Pollution.gif", []),
]

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

        semaphore = asyncio.Semaphore(CONCURRENCY)
        counter = 0

        async def pull(index: int, path: str, pairs: QueryPairs) -> None:
            query = canonical_query(pairs)
            async with semaphore:
                try:
                    r = await client.get(f"{base}{path}", params=tuple(pairs), headers=headers)
                except httpx.HTTPError as exc:
                    manifest.failures.append({"path": path, "query": query, "reason": str(exc)})
                    return
            if r.status_code != 200:
                manifest.failures.append(
                    {"path": path, "query": query, "reason": f"HTTP {r.status_code}"}
                )
                return
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

        tasks = []
        for path, pairs in endpoints:
            counter += 1
            tasks.append(pull(counter, path, pairs))
        await asyncio.gather(*tasks)
    finally:
        if owns_client:
            await client.aclose()

    manifest.entries.sort(key=lambda e: e.file)
    manifest.save(out_dir)
    return manifest
