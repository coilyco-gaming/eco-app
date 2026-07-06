"""Item index + per-item pivot — every item ever bought / sold / crafted.

Two surfaces sit on top of the existing trades ledger (`trades.py`) and crafting
atlas (`crafting.py`), both of which already stream the `/api/v1/exporter/actions`
CSVs and join numeric ids to citizen names:

* **Item index** (`fetch_item_index`) — the union of every item that shows up in
  the trades ledger's `by_item` and the crafting atlas's `by_item`, with the
  trade count / currency volume / crafted quantity carried alongside. This is the
  `/items` list page.

* **Item pivot** (`fetch_item_pivot`) — for one item id, every field that pivots
  on it: the individual trade rows (who bought/sold it, for how much) and the
  individual crafting events (who made it, at which station), newest first. This
  is the `/item?item=<id>` detail page.

The index reuses the two cached aggregates, so it's cheap. The pivot re-streams
the crafting CSVs to recover per-event rows (the atlas only keeps aggregates), so
it carries its own short TTL cache keyed per (base_url, api_key_hash, item) to
stay off the admin endpoint on rapid re-renders. Trade rows come from the shared
`trades.fetch_parsed_trades` spine, filtered to the item.

Everything is keyed on the Day 3 sparse-state: "no events yet" / "item never
seen" is a valid response, not an error (mirrors crafting.py, eco-app#5).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import httpx
from cachetools import TTLCache

from .crafting import (
    _INT_RE,
    _NONSENSE_KEY_RE,
    CRAFT_ACTION_TYPES,
    MAX_ROWS_PER_ACTION,
    _corrected_index,
    _normalize_admin_base,
    _now_iso,
    _stream_csv_rows,
    fetch_atlas,
    fetch_citizen_name_map,
)
from .trades import SECONDS_PER_DAY, _label, fetch_ledger, fetch_parsed_trades

DEFAULT_CACHE_TTL_S = float(os.environ.get("ECO_ITEMS_CACHE_TTL", "60"))

# Per-surface caps: the detail tables are browsable, not exhaustive. Newest
# events win the cap; the summary counts still cover every row.
MAX_PIVOT_TRADES = int(os.environ.get("ECO_ITEMS_PIVOT_TRADES", "500"))
MAX_PIVOT_CRAFTS = int(os.environ.get("ECO_ITEMS_PIVOT_CRAFTS", "500"))

_pivot_cache: TTLCache[str, ItemPivot] = TTLCache(maxsize=128, ttl=DEFAULT_CACHE_TTL_S)


def _cache_key(base_url: str, api_key: str | None, item: str) -> str:
    token = hashlib.sha256((api_key or "").encode()).hexdigest()[:12]
    return f"{base_url}|{token}|{item}"


@dataclass
class ItemIndex:
    """The `/items` list surface — one row per distinct item. JSON-serializable."""

    fetched_at_iso: str
    source_base_url: str
    # Each dict is {item, tradeCount, tradeVolume, craftCount}, already camelCase.
    items: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fetchedAtISO": self.fetched_at_iso,
            "sourceBaseUrl": self.source_base_url,
            "totalItems": len(self.items),
            "items": list(self.items),
            "warnings": list(self.warnings),
        }


@dataclass
class _CraftEvent:
    """One crafting/production event before id->name resolution."""

    action_type: str
    time_s: float
    day: float
    citizen_id: str
    station: str
    quantity: float


@dataclass
class ItemPivot:
    """The `/item?item=<id>` detail surface. JSON-serializable."""

    fetched_at_iso: str
    source_base_url: str
    item: str
    # Individual trade rows for this item, newest first, capped. Same camelCase
    # shape as a trades-ledger row (see trades._row_dict).
    trades: list[dict[str, Any]] = field(default_factory=list)
    # Individual crafting events for this item, newest first, capped.
    crafts: list[dict[str, Any]] = field(default_factory=list)
    trade_count: int = 0
    trade_volume: float = 0.0
    craft_count: int = 0
    craft_quantity: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fetchedAtISO": self.fetched_at_iso,
            "sourceBaseUrl": self.source_base_url,
            "item": self.item,
            "trades": list(self.trades),
            "crafts": list(self.crafts),
            "tradeCount": self.trade_count,
            "tradeVolume": self.trade_volume,
            "craftCount": self.craft_count,
            "craftQuantity": self.craft_quantity,
            "warnings": list(self.warnings),
        }


def _dedupe(seq: Iterable[str]) -> list[str]:
    """Order-preserving de-dupe — the ledger + atlas may warn about the same
    citizens join twice, and one warning line is enough."""
    seen: set[str] = set()
    out: list[str] = []
    for s in seq:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def build_item_index(
    ledger_by_item: list[tuple[str, int, float]],
    atlas_by_item: list[tuple[str, float]],
    fetched_at_iso: str,
    source_base_url: str,
    warnings: Iterable[str] = (),
) -> ItemIndex:
    """Merge the trades + crafting per-item aggregates into one ranked list.

    `ledger_by_item` is `(item, trade_count, currency_volume)`; `atlas_by_item`
    is `(item, crafted_quantity)`. An item can appear in either or both. Ranked
    by total activity (trades + crafted quantity), volume breaking ties, so the
    busiest items sit at the top of the directory.
    """
    trade_map = {item: (cnt, vol) for item, cnt, vol in ledger_by_item}
    craft_map = {item: qty for item, qty in atlas_by_item}
    items: list[dict[str, Any]] = []
    for item in set(trade_map) | set(craft_map):
        trade_count, trade_volume = trade_map.get(item, (0, 0.0))
        craft_count = craft_map.get(item, 0.0)
        items.append(
            {
                "item": item,
                "tradeCount": trade_count,
                "tradeVolume": trade_volume,
                "craftCount": craft_count,
            }
        )
    items.sort(
        key=lambda r: (r["tradeCount"] + r["craftCount"], r["tradeVolume"]),
        reverse=True,
    )
    return ItemIndex(
        fetched_at_iso=fetched_at_iso,
        source_base_url=source_base_url,
        items=items,
        warnings=_dedupe(warnings),
    )


async def fetch_item_index(
    base_url: str | None = None,
    api_key: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> ItemIndex:
    """Build the item directory from the (cached) trades ledger + crafting atlas."""
    normalized = _normalize_admin_base(base_url)
    ledger, atlas = await asyncio.gather(
        fetch_ledger(base_url=base_url, api_key=api_key, client=client),
        fetch_atlas(base_url=base_url, api_key=api_key, client=client),
    )
    # The atlas splits production into crafted units (by_crafted) and gathered
    # events (by_gathered) since eco-app#70; the item directory unions both — an
    # item is "produced" whether it was bench-crafted or harvested/mined.
    craft_totals: dict[str, float] = {}
    for name, value in (*atlas.by_crafted, *atlas.by_gathered):
        craft_totals[name] = craft_totals.get(name, 0.0) + value
    return build_item_index(
        ledger.by_item,
        list(craft_totals.items()),
        fetched_at_iso=_now_iso(),
        source_base_url=normalized,
        warnings=[*ledger.warnings, *atlas.warnings],
    )


def parse_craft_events(
    action_name: str,
    rows: Iterable[list[str]],
    target_item: str,
    events: list[_CraftEvent],
    max_rows: int = MAX_ROWS_PER_ACTION,
) -> int:
    """Fold one action's CSV rows into `events`, keeping only rows for `target_item`.

    Mirrors `crafting.aggregate_rows`' column picks (the produced item is
    ItemUsed for crafts, Species for harvest/chop, the block for mining), but
    retains per-event rows for one item instead of aggregating. Returns the
    number of data rows consumed (excluding the header), so a batched caller can
    respect the per-action row cap.
    """
    it = iter(rows)
    try:
        header = next(it)
    except StopIteration:
        return 0

    col = {name: i for i, name in enumerate(header)}

    def pick(row: list[str], idx: list[int], *candidates: str) -> str:
        for c in candidates:
            j = col.get(c)
            if j is not None and idx[j] < len(row):
                v = row[idx[j]].strip()
                if v:
                    return v
        return ""

    consumed = 0
    for row in it:
        if not row:
            continue
        if consumed >= max_rows:
            break
        idx = _corrected_index(header, row)
        item = pick(row, idx, "ItemUsed", "Species", "BlockItemOnDestroy", "BlockDestroyed")
        if item and _NONSENSE_KEY_RE.match(item):
            item = ""
        consumed += 1
        if item != target_item:
            continue
        try:
            quantity = float(pick(row, idx, "Count") or "0")
        except ValueError:
            quantity = 0.0
        station = pick(row, idx, "WorldObjectItem", "ToolUsed") or "(hand)"
        if _NONSENSE_KEY_RE.match(station):
            station = "(hand)"
        citizen = pick(row, idx, "Citizen")
        try:
            time_s = float(pick(row, idx, "Time") or "0")
        except ValueError:
            time_s = 0.0
        events.append(
            _CraftEvent(
                action_type=action_name,
                time_s=time_s,
                day=time_s / SECONDS_PER_DAY,
                citizen_id=citizen if _INT_RE.match(citizen) else "",
                station=station,
                quantity=quantity,
            )
        )
    return consumed


async def _fetch_craft_events(
    item: str,
    normalized_base: str,
    headers: dict[str, str],
    http: httpx.AsyncClient,
    warnings: list[str],
) -> list[_CraftEvent]:
    """Stream every craft action CSV, keeping only per-event rows for `item`.

    The crafting atlas discards individual rows, so the pivot re-streams them.
    We only ever hold the events for the one requested item plus a bounded parse
    batch, so this stays memory-safe even on late-cycle multi-MB CSVs.
    """
    events: list[_CraftEvent] = []
    for action in CRAFT_ACTION_TYPES:
        url = f"{normalized_base}/api/v1/exporter/actions?actionName={action}"
        try:
            remaining = MAX_ROWS_PER_ACTION
            header: list[str] | None = None
            batch: list[list[str]] = []
            async for row in _stream_csv_rows(http, url, headers):
                if header is None:
                    header = row
                    batch = [row]
                    continue
                batch.append(row)
                if len(batch) >= 1024:
                    consumed = parse_craft_events(action, batch, item, events, max_rows=remaining)
                    remaining -= consumed
                    if remaining <= 0:
                        break
                    batch = [header]
            if header is not None and len(batch) > 1 and remaining > 0:
                parse_craft_events(action, batch, item, events, max_rows=remaining)
        except httpx.HTTPStatusError as e:
            warnings.append(f"{action}: HTTP {e.response.status_code}")
        except httpx.HTTPError as e:
            warnings.append(f"{action}: {type(e).__name__}: {e}")
    return events


def _craft_row_dict(e: _CraftEvent, name_map: dict[str, str]) -> dict[str, Any]:
    """One crafting event, camelCase, with the citizen id resolved to a name."""
    return {
        "actionType": e.action_type,
        "time": e.time_s,
        "day": e.day,
        "citizen": _label(e.citizen_id, name_map),
        "station": e.station,
        "quantity": e.quantity,
    }


async def fetch_item_pivot(
    item: str,
    base_url: str | None = None,
    api_key: str | None = None,
    cache_ttl_s: float = DEFAULT_CACHE_TTL_S,
    client: httpx.AsyncClient | None = None,
) -> ItemPivot:
    """Every trade + crafting event that pivots on one item id, newest first.

    Trade rows come from the shared `trades.fetch_parsed_trades` spine (filtered
    to the item); craft rows are re-streamed here since the atlas only keeps
    aggregates. Both id->name joins reuse the citizens surface. Result is cached
    per (base_url, api_key_hash, item) for a short TTL.
    """
    normalized = _normalize_admin_base(base_url)
    key = _cache_key(normalized, api_key, item)
    if cache_ttl_s > 0:
        cached = _pivot_cache.get(key)
        if cached is not None:
            return cached

    pivot = ItemPivot(fetched_at_iso=_now_iso(), source_base_url=normalized, item=item)
    headers = {"X-API-Key": api_key} if api_key else {}

    # Trade leg: reuse the parsed-trades spine, then filter + resolve names.
    fetch = await fetch_parsed_trades(base_url=base_url, api_key=api_key, client=client)
    from .trades import _row_dict  # local import: avoids a module-load cycle

    item_trades = [t for t in fetch.parsed if t.item == item]
    item_trades.sort(key=lambda t: t.time_s, reverse=True)
    pivot.trade_count = len(item_trades)
    pivot.trade_volume = sum(t.currency_amount for t in item_trades)
    pivot.trades = [_row_dict(t, fetch.name_map) for t in item_trades[:MAX_PIVOT_TRADES]]
    pivot.warnings.extend(fetch.warnings)

    # Craft leg: re-stream the production CSVs for this one item.
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0))
    try:
        craft_warnings: list[str] = []
        events = await _fetch_craft_events(item, normalized, headers, http, craft_warnings)
        events.sort(key=lambda e: e.time_s, reverse=True)
        pivot.craft_count = len(events)
        pivot.craft_quantity = sum(e.quantity for e in events)
        name_map: dict[str, str] = {}
        if any(e.citizen_id for e in events):
            name_map = await fetch_citizen_name_map(http, normalized, headers, craft_warnings)
        pivot.crafts = [_craft_row_dict(e, name_map) for e in events[:MAX_PIVOT_CRAFTS]]
        pivot.warnings.extend(craft_warnings)
    finally:
        if owns_client:
            await http.aclose()

    pivot.warnings = _dedupe(pivot.warnings)
    if cache_ttl_s > 0:
        _pivot_cache[key] = pivot
    return pivot


def _clear_cache() -> None:
    """Test helper — drop the in-process pivot cache between cases."""
    _pivot_cache.clear()
