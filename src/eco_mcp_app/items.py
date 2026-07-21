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
    CRAFTED_ACTION_TYPE,
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

# Per-leg caps: how many raw trade / craft rows we carry before merging. Raised
# from 500 (eco-app#92) so the compressed feed below is comprehensive enough for
# real pagination rather than a client-side slice of the first 200 rows. The
# summary counts still cover *every* row (they're computed pre-cap).
MAX_PIVOT_TRADES = int(os.environ.get("ECO_ITEMS_PIVOT_TRADES", "2000"))
MAX_PIVOT_CRAFTS = int(os.environ.get("ECO_ITEMS_PIVOT_CRAFTS", "2000"))

# The merged reverse-chrono feed is compressed (runs of identical rows collapse
# to one counted row, eco-app#92), so it stays small even for an item crafted
# tens of thousands of times. This caps the compressed row count the payload
# ships; a truncation warning keeps any drop visible rather than silent.
MAX_FEED_ROWS = int(os.environ.get("ECO_ITEMS_FEED_ROWS", "1000"))

# Per-summary detail caps — the actionable top-of-page card stays lean.
TOP_CRAFTERS = int(os.environ.get("ECO_ITEMS_TOP_CRAFTERS", "12"))
TOP_SUPPLY_OFFERS = int(os.environ.get("ECO_ITEMS_TOP_OFFERS", "8"))

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
    # Merged reverse-chrono timeline (crafts + trades interleaved), with runs of
    # identical consecutive rows collapsed to one counted row. This is the SPA's
    # primary surface; `trades` / `crafts` above stay for other consumers.
    feed: list[dict[str, Any]] = field(default_factory=list)
    feed_truncated: bool = False
    # Actionable top-of-page summary: who makes it, what's for sale now, who's
    # buying. Pulled off the trades + logistics spine. See `_build_summary`.
    summary: dict[str, Any] = field(default_factory=dict)
    # The world clock (`TimeSinceStart`, in-game seconds) so the SPA can render
    # "X ago" against real "now" rather than the newest event on the page. None
    # when /info was unreachable — the SPA then falls back to newest-as-now.
    world_clock_s: float | None = None
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
            "feed": list(self.feed),
            "feedTruncated": self.feed_truncated,
            "summary": dict(self.summary),
            "worldClockS": self.world_clock_s,
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
        # A craft row with Count > 1 is a per-citizen hourly rollup whose item
        # label is one arbitrary merged event - not this item's craft. Skip it
        # so the pivot never re-manufactures "Theo crafted 32 stump latrines"
        # (eco-app#131). Gather rows keep their Count (biomass magnitude).
        if action_name == CRAFTED_ACTION_TYPE and quantity > 1.0:
            continue
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


# ---------------------------------------------------------------------------
# Merged, compressed, reverse-chrono feed (eco-app#92).
# ---------------------------------------------------------------------------


def _craft_feed_row(c: dict[str, Any]) -> dict[str, Any]:
    """Normalize one craft row into a feed row (a single-count run to start)."""
    return {
        "kind": "craft",
        "time": c["time"],
        "day": c["day"],
        "actor": c.get("citizen") or "",
        "actionType": c.get("actionType") or "",
        "station": c.get("station") or "",
        "quantity": float(c.get("quantity") or 0.0),
        # Trade-only fields, present-but-empty so the row shape is uniform.
        "buyer": "",
        "seller": "",
        "currency": "",
        "unitPrice": None,
        "currencyAmount": 0.0,
        "runCount": 1,
        "spanSeconds": 0.0,
    }


def _trade_feed_row(t: dict[str, Any]) -> dict[str, Any]:
    """Normalize one trade row into a feed row (a single-count run to start)."""
    return {
        "kind": "trade",
        "time": t["time"],
        "day": t["day"],
        "actor": t.get("seller") or "",
        "actionType": t.get("tradeType") or "",
        "station": t.get("store") or "",
        "quantity": float(t.get("quantity") or 0.0),
        "buyer": t.get("buyer") or "",
        "seller": t.get("seller") or "",
        "currency": t.get("currency") or "",
        "unitPrice": t.get("unitPrice"),
        "currencyAmount": float(t.get("currencyAmount") or 0.0),
        "runCount": 1,
        "spanSeconds": 0.0,
    }


def _feed_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    """The identity a run of consecutive rows must share to collapse.

    Crafts fold on (actor, verb, station) — "Rechim crafted Hewn Log at
    Carpentry Table" repeated. Trades fold on (seller, buyer, currency,
    unit-price) so an identical repeated fill collapses too, but a different
    price or counterparty stays its own row.
    """
    if row["kind"] == "craft":
        return ("craft", row["actor"], row["actionType"], row["station"])
    price = row["unitPrice"]
    price_key = round(price, 4) if isinstance(price, (int, float)) else None
    return ("trade", row["seller"], row["buyer"], row["currency"], price_key)


def build_item_feed(
    trade_rows: Iterable[dict[str, Any]],
    craft_rows: Iterable[dict[str, Any]],
    *,
    max_rows: int = MAX_FEED_ROWS,
) -> tuple[list[dict[str, Any]], bool]:
    """Merge trades + crafts into one reverse-chrono feed, compressing repeats.

    Pure. Rows are the camelCase dicts `_row_dict` / `_craft_row_dict` produce.
    Consecutive rows sharing a `_feed_signature` collapse into one row whose
    `runCount` is the number folded, `quantity` / `currencyAmount` are summed,
    `time` / `day` are the newest in the run, and `spanSeconds` is how long the
    run took (newest minus oldest). Returns `(feed, truncated)` where `truncated`
    flags that the compressed feed hit `max_rows`.
    """
    rows = [_trade_feed_row(t) for t in trade_rows]
    rows.extend(_craft_feed_row(c) for c in craft_rows)
    # Newest first. `sorted` is stable, so equal-time crafts and trades keep a
    # deterministic order (crafts were appended after trades) — matters only for
    # the rare exact-second tie and keeps the output reproducible for tests.
    rows.sort(key=lambda r: r["time"], reverse=True)

    feed: list[dict[str, Any]] = []
    truncated = False
    for row in rows:
        prev = feed[-1] if feed else None
        if prev is not None and _feed_signature(prev) == _feed_signature(row):
            # Fold into the open run. `prev.time` is the newest (we're descending),
            # so the incoming row is older or equal — it extends the span's tail.
            prev["runCount"] += 1
            prev["quantity"] += row["quantity"]
            prev["currencyAmount"] += row["currencyAmount"]
            prev["spanSeconds"] = prev["time"] - row["time"]
            continue
        if len(feed) >= max_rows:
            truncated = True
            break
        feed.append(row)
    return feed, truncated


def _crafter_ranks(
    events: list[_CraftEvent], name_map: dict[str, str], *, top: int = TOP_CRAFTERS
) -> list[dict[str, Any]]:
    """Fold craft events into a per-crafter leaderboard, most produced first.

    This is the "who can make it" half of the actionable summary: every citizen
    who has produced the item, ranked by total quantity, with their event count
    alongside so a few bulk crafts read differently from many small ones.
    """
    folded: dict[str, dict[str, Any]] = {}
    for e in events:
        name = _label(e.citizen_id, name_map) or "someone"
        row = folded.get(name)
        if row is None:
            folded[name] = {"name": name, "quantity": e.quantity, "events": 1}
        else:
            row["quantity"] += e.quantity
            row["events"] += 1
    ranked = sorted(folded.values(), key=lambda r: (r["quantity"], r["events"]), reverse=True)
    return [
        {"name": r["name"], "quantity": round(r["quantity"], 2), "events": r["events"]}
        for r in ranked[:top]
    ]


def _shelf_side(report: Any, board: str, *, top: int) -> dict[str, Any]:
    """Flatten one logistics board (already item-filtered) into a supply/demand block.

    `board` is `"cheapest"` (stores selling → supply) or `"resale"` (stores
    buying → demand). Each board row is per (item, currency) and carries up to
    `TOP_PER_ITEM` offers; we flatten across currencies, sum stock/wanted
    quantities, and cap the offer list. `capped` flags that a market had more
    distinct stores than the offers we can show, so the total is a floor.
    """
    rows = getattr(report, board, [])
    offers: list[dict[str, Any]] = []
    total_qty = 0.0
    store_keys: set[str] = set()
    count_key = "sellerCount" if board == "cheapest" else "buyerCount"
    capped = False
    for r in rows:
        row_offers = r.get("offers", [])
        if len(row_offers) < r.get(count_key, 0):
            capped = True
        for o in row_offers:
            offers.append(
                {
                    "store": o.get("store"),
                    "owner": o.get("owner"),
                    "price": o.get("price"),
                    "quantity": o.get("quantity"),
                    "currency": o.get("currency"),
                    "source": o.get("source"),
                }
            )
            total_qty += float(o.get("quantity") or 0.0)
            store_keys.add(o.get("storeKey") or o.get("store") or "")
    # Sellers cheapest first, buyers best-paid first.
    offers.sort(key=lambda o: o.get("price") or 0.0, reverse=(board == "resale"))
    return {
        "storeCount": len(store_keys),
        "totalQuantity": round(total_qty, 2),
        "offers": offers[:top],
        "capped": capped,
    }


async def _fetch_world_clock(
    http: httpx.AsyncClient, normalized_base: str, headers: dict[str, str]
) -> float | None:
    """Best-effort read of the world clock (`TimeSinceStart`) off `/info`.

    Public endpoint (no key needed), same as the currency route uses. Absence /
    fault is non-fatal — the SPA falls back to newest-event-as-now.
    """
    try:
        resp = await http.get(f"{normalized_base}/info", headers=headers)
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return None
    tss = data.get("TimeSinceStart") if isinstance(data, dict) else None
    try:
        return float(tss) if tss is not None else None
    except (TypeError, ValueError):
        return None


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
    all_trade_rows = [_row_dict(t, fetch.name_map) for t in item_trades]
    pivot.trades = all_trade_rows[:MAX_PIVOT_TRADES]
    pivot.warnings.extend(fetch.warnings)

    # Craft leg: re-stream the production CSVs for this one item.
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0))
    all_craft_rows: list[dict[str, Any]] = []
    crafters: list[dict[str, Any]] = []
    supply: dict[str, Any] = {}
    demand: dict[str, Any] = {}
    live_shelf = False
    try:
        craft_warnings: list[str] = []
        events = await _fetch_craft_events(item, normalized, headers, http, craft_warnings)
        events.sort(key=lambda e: e.time_s, reverse=True)
        pivot.craft_count = len(events)
        pivot.craft_quantity = sum(e.quantity for e in events)
        name_map: dict[str, str] = {}
        if any(e.citizen_id for e in events):
            name_map = await fetch_citizen_name_map(http, normalized, headers, craft_warnings)
        all_craft_rows = [_craft_row_dict(e, name_map) for e in events]
        pivot.crafts = all_craft_rows[:MAX_PIVOT_CRAFTS]
        crafters = _crafter_ranks(events, name_map)
        pivot.warnings.extend(craft_warnings)

        # World clock — best-effort, so "X ago" reads against real "now".
        pivot.world_clock_s = await _fetch_world_clock(http, normalized, headers)

        # Supply / demand — fold the item-filtered logistics boards (the same
        # history + live-shelf spine `/trade` uses). Best-effort: the trades leg
        # already succeeded and logistics reuses that cache, so a fault here is
        # a degraded summary, never a failed pivot.
        from .logistics import fetch_logistics  # local import: avoids a cycle

        try:
            report = await fetch_logistics(
                base_url=base_url, api_key=api_key, item=item, client=http
            )
            live_shelf = report.live
            supply = _shelf_side(report, "cheapest", top=TOP_SUPPLY_OFFERS)
            demand = _shelf_side(report, "resale", top=TOP_SUPPLY_OFFERS)
        except httpx.HTTPError as e:
            pivot.warnings.append(f"logistics: {type(e).__name__} (supply/demand unavailable)")
    finally:
        if owns_client:
            await http.aclose()

    pivot.feed, pivot.feed_truncated = build_item_feed(all_trade_rows, all_craft_rows)
    if pivot.feed_truncated:
        pivot.warnings.append(
            f"feed truncated to {MAX_FEED_ROWS} compressed rows (summary counts still cover all)"
        )
    pivot.summary = {
        "crafters": crafters,
        "supply": supply,
        "demand": demand,
        "live": live_shelf,
    }

    pivot.warnings = _dedupe(pivot.warnings)
    if cache_ttl_s > 0:
        _pivot_cache[key] = pivot
    return pivot


def _clear_cache() -> None:
    """Test helper — drop the in-process pivot cache between cases."""
    _pivot_cache.clear()
