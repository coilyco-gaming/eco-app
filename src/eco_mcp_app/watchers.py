"""Host-agnostic trade watchers (eco-app#52).

DiscordLink ships `WatchTradeFeed` (an event stream to a Discord DM) and
`WatchTradeDisplay` (a self-updating snapshot), plus `UnwatchTradeFeed/Display`
and `ListTradeWatchers`. The epic thesis (eco-app#37) is that this read-only
info belongs on **the website**, not a Discord DM. This module meets those
verbs and exceeds them by being host-agnostic: watchers are surfaced on the SPA
`/trade` route and queryable over MCP, so a URL-connected host like claude.ai
can ask "what did my watchers catch." No Discord dependency.

## No-reset spine

Watchers evaluate against the `CurrencyTrade` / `BarterTrade` history the server
**already exports** (see `trades.py`). Each evaluation diffs the newest trades
against stored watch queries — no new C# mod, no server reset. The two
DiscordLink semantics fall out of one pass over the ledger:

* **Feed** — trades matching the query with `time` past the watcher's stored
  last-seen mark. This is the event-stream semantic: each matching trade is
  surfaced exactly once, then the mark advances past it.
* **Display** — the *current* matching state: how many trades match right now,
  the most recent handful, the cheapest unit price seen, total volume. This is
  the self-updating-snapshot semantic and it does not consume the feed mark.

## Persistence

A small SQLite store at `~/.cache/eco-mcp-app/watchers.sqlite`, mirroring the
fair-price cache pattern (`fair_price.default_cache_dir()`, so
`ECO_MCP_CACHE_DIR` relocates both). One row per watcher, keyed by id, carrying
the query, the last-seen timestamp, and the creation time. The schema is created
idempotently on first open and survives a process restart.

## Query kinds

* `item` — match a trade's item (raw Eco name or its prettified form).
* `store` — match the store (`WorldObjectItem`) the trade happened at.
* `trader` — match any party (buyer, seller, or shop owner) by resolved name.
* `price` — an item plus a threshold predicate on unit price, e.g. "iron ingot
  under 2.5". This is the exceeds-DiscordLink predicate: a numeric filter, not
  just a name match.

Matching is case-insensitive substring for the name kinds; `price` additionally
requires the trade to carry a unit price on the matched item.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .crafting import prettify_eco_name
from .fair_price import default_cache_dir

# The kinds a watcher query can take. `price` carries an op + threshold; the
# other three are pure name-substring matches against a specific trade field.
WATCH_KINDS = ("item", "store", "trader", "price")

# How many matching trades the display block echoes back (newest first). The
# feed block is uncapped within one evaluation — a watcher that has been quiet
# for a while should catch every trade it missed — but a single evaluation only
# ever sees the ledger's own newest-N window (`trades.MAX_LEDGER_ROWS`).
DISPLAY_RECENT = 12

# Accepted spellings for the price predicate, normalized to "under" / "over".
_UNDER_ALIASES = {"under", "below", "lt", "<", "<=", "le"}
_OVER_ALIASES = {"over", "above", "gt", ">", ">=", "ge"}


class WatcherError(ValueError):
    """Raised for an invalid watcher spec (bad kind, missing threshold, …).

    A `ValueError` subclass so the MCP tool layer can turn it into a clean
    user-facing error rather than a 500.
    """


def normalize_op(op: str | None) -> str | None:
    """Map a threshold operator spelling to `under` / `over`, or None."""
    if not op:
        return None
    key = op.strip().lower()
    if key in _UNDER_ALIASES:
        return "under"
    if key in _OVER_ALIASES:
        return "over"
    return None


@dataclass
class WatchQuery:
    """The predicate half of a watcher, independent of its stored state."""

    kind: str
    value: str
    op: str | None = None
    threshold: float | None = None

    def describe(self) -> str:
        """Human phrase for the query, e.g. `iron ingot under 2.5`."""
        pretty = prettify_eco_name(self.value) if self.value else self.value
        if self.kind == "price":
            return f"{pretty} {self.op} {self.threshold:g}"
        return f"{self.kind}: {pretty}"


@dataclass
class Watcher:
    """A stored watcher: its query plus persistence bookkeeping."""

    id: str
    query: WatchQuery
    label: str
    server: str | None = None
    last_seen: float = 0.0
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.query.kind,
            "value": self.query.value,
            "op": self.query.op,
            "threshold": self.query.threshold,
            "label": self.label,
            "server": self.server,
            "lastSeen": self.last_seen,
            "createdAt": self.created_at,
            "describe": self.query.describe(),
        }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def build_query(
    kind: str,
    value: str,
    op: str | None = None,
    threshold: float | None = None,
) -> WatchQuery:
    """Validate + normalize a raw query spec into a `WatchQuery`.

    Raises `WatcherError` on anything the evaluator couldn't act on: an unknown
    kind, an empty value, or a `price` query missing its operator / threshold.
    """
    k = (kind or "").strip().lower()
    if k not in WATCH_KINDS:
        raise WatcherError(
            f"unknown watcher kind '{kind}'; expected one of {', '.join(WATCH_KINDS)}"
        )
    v = (value or "").strip()
    if not v:
        raise WatcherError("watcher value must not be empty (the item / store / trader to watch)")
    if k == "price":
        norm_op = normalize_op(op)
        if norm_op is None:
            raise WatcherError("price watcher needs an operator: 'under' or 'over'")
        if threshold is None:
            raise WatcherError("price watcher needs a numeric threshold (e.g. 2.5)")
        try:
            thr = float(threshold)
        except (TypeError, ValueError) as e:
            raise WatcherError(f"price threshold '{threshold}' is not a number") from e
        return WatchQuery(kind="price", value=v, op=norm_op, threshold=thr)
    return WatchQuery(kind=k, value=v)


# ---------------------------------------------------------------------------
# SQLite store
# ---------------------------------------------------------------------------


def _watchers_db_path() -> Any:
    d = default_cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "watchers.sqlite"


def _open_store() -> sqlite3.Connection:
    conn = sqlite3.connect(_watchers_db_path())
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS watchers (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            value TEXT NOT NULL,
            op TEXT,
            threshold REAL,
            label TEXT NOT NULL,
            server TEXT,
            last_seen REAL NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
        )
        """
    )
    return conn


def _row_to_watcher(row: tuple[Any, ...]) -> Watcher:
    wid, kind, value, op, threshold, label, server, last_seen, created_at = row
    return Watcher(
        id=wid,
        query=WatchQuery(kind=kind, value=value, op=op, threshold=threshold),
        label=label,
        server=server,
        last_seen=float(last_seen),
        created_at=float(created_at),
    )


def create_watcher(
    query: WatchQuery, label: str | None = None, server: str | None = None
) -> Watcher:
    """Persist a new watcher and return it (id + timestamps filled in).

    `last_seen` starts at 0 so the first evaluation treats every current match
    as a fresh feed hit (a new watcher's display and feed agree on the first
    poll), then the mark advances past what it surfaced.
    """
    wid = "w_" + uuid.uuid4().hex[:12]
    now = time.time()
    resolved_label = (label or query.describe()).strip()
    watcher = Watcher(
        id=wid, query=query, label=resolved_label, server=server, last_seen=0.0, created_at=now
    )
    with _open_store() as conn:
        conn.execute(
            "INSERT INTO watchers "
            "(id, kind, value, op, threshold, label, server, last_seen, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                watcher.id,
                query.kind,
                query.value,
                query.op,
                query.threshold,
                resolved_label,
                server,
                0.0,
                now,
            ),
        )
    return watcher


def list_watchers() -> list[Watcher]:
    """All stored watchers, newest first."""
    with _open_store() as conn:
        rows = conn.execute(
            "SELECT id, kind, value, op, threshold, label, server, last_seen, created_at "
            "FROM watchers ORDER BY created_at DESC"
        ).fetchall()
    return [_row_to_watcher(r) for r in rows]


def get_watcher(watcher_id: str) -> Watcher | None:
    with _open_store() as conn:
        row = conn.execute(
            "SELECT id, kind, value, op, threshold, label, server, last_seen, created_at "
            "FROM watchers WHERE id = ?",
            (watcher_id,),
        ).fetchone()
    return _row_to_watcher(row) if row else None


def remove_watcher(watcher_id: str) -> bool:
    """Delete a watcher by id. Returns True if a row was removed."""
    with _open_store() as conn:
        cur = conn.execute("DELETE FROM watchers WHERE id = ?", (watcher_id,))
        return cur.rowcount > 0


def _advance_last_seen(watcher_id: str, last_seen: float) -> None:
    with _open_store() as conn:
        conn.execute(
            "UPDATE watchers SET last_seen = ? WHERE id = ?",
            (last_seen, watcher_id),
        )


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def _item_haystack(trade: dict[str, Any]) -> str:
    """Lowercase raw + prettified item name, so 'iron ingot' and 'IronIngot' hit."""
    item = trade.get("item") or ""
    pretty = prettify_eco_name(item) if item else ""
    return f"{item} {pretty}".lower()


def trade_matches(query: WatchQuery, trade: dict[str, Any]) -> bool:
    """True if `trade` (a camelCase ledger row) satisfies the query.

    Name kinds are case-insensitive substring matches. `price` requires the
    item to match *and* the trade to carry a unit price on the right side of
    the threshold — a barter row or an unpriced trade never matches a price
    watcher.
    """
    needle = query.value.strip().lower()
    if not needle:
        return False
    if query.kind == "item":
        return needle in _item_haystack(trade)
    if query.kind == "store":
        return needle in (trade.get("store") or "").lower()
    if query.kind == "trader":
        parties = " ".join(
            str(trade.get(role) or "") for role in ("buyer", "seller", "shopOwner")
        ).lower()
        return needle in parties
    if query.kind == "price":
        if needle not in _item_haystack(trade):
            return False
        unit = trade.get("unitPrice")
        if unit is None or query.threshold is None:
            return False
        if query.op == "under":
            return float(unit) < query.threshold
        if query.op == "over":
            return float(unit) > query.threshold
        return False
    return False


@dataclass
class WatcherHit:
    """One watcher's evaluation against a ledger: feed + display + new mark."""

    watcher: Watcher
    feed: list[dict[str, Any]] = field(default_factory=list)
    matches: list[dict[str, Any]] = field(default_factory=list)
    new_last_seen: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        best_price = min(
            (m["unitPrice"] for m in self.matches if m.get("unitPrice") is not None),
            default=None,
        )
        total_volume = sum(float(m.get("currencyAmount") or 0.0) for m in self.matches)
        last_match_time = max((float(m.get("time") or 0.0) for m in self.matches), default=None)
        return {
            **self.watcher.to_dict(),
            # Feed semantic: matching trades new since the last-seen mark.
            "feed": list(self.feed),
            "feedCount": len(self.feed),
            # Display semantic: the current matching state as a self-updating
            # snapshot. Independent of the feed mark.
            "display": {
                "matchCount": len(self.matches),
                "recent": self.matches[:DISPLAY_RECENT],
                "bestUnitPrice": best_price,
                "totalVolume": total_volume,
                "lastMatchTime": last_match_time,
            },
            "newLastSeen": self.new_last_seen,
        }


def evaluate_watcher(watcher: Watcher, trades: list[dict[str, Any]]) -> WatcherHit:
    """Evaluate one watcher against ledger rows (newest-first). Pure — no I/O.

    `feed` is the matching rows strictly newer than `watcher.last_seen`;
    `matches` is every matching row (the display snapshot). `new_last_seen`
    advances to the newest matching row's time (never backwards), so a caller
    that persists it consumes each feed hit exactly once.
    """
    matches = [t for t in trades if trade_matches(watcher.query, t)]
    matches.sort(key=lambda t: float(t.get("time") or 0.0), reverse=True)
    feed = [t for t in matches if float(t.get("time") or 0.0) > watcher.last_seen]
    newest = max((float(t.get("time") or 0.0) for t in matches), default=watcher.last_seen)
    new_last_seen = max(watcher.last_seen, newest)
    return WatcherHit(watcher=watcher, feed=feed, matches=matches, new_last_seen=new_last_seen)


def evaluate_all(trades: list[dict[str, Any]], advance: bool = True) -> list[WatcherHit]:
    """Evaluate every stored watcher against `trades`.

    When `advance` is True (the feed semantic, used by the MCP `evaluate`
    action), each watcher's last-seen mark is persisted forward so its feed
    hits aren't re-surfaced. When False (the display semantic, used by the SPA
    poll), the store is left untouched — viewing the website never consumes a
    feed.
    """
    hits = [evaluate_watcher(w, trades) for w in list_watchers()]
    if advance:
        for hit in hits:
            if hit.new_last_seen > hit.watcher.last_seen:
                _advance_last_seen(hit.watcher.id, hit.new_last_seen)
                hit.watcher.last_seen = hit.new_last_seen
    return hits


# ---------------------------------------------------------------------------
# Markdown (MCP hosts without the SPA)
# ---------------------------------------------------------------------------


def watchers_list_markdown(watchers: list[Watcher]) -> str:
    """Compact list of the stored watchers for an MCP text block."""
    if not watchers:
        return (
            "**Trade watchers** — none yet. Create one with "
            "`action=create` (e.g. kind=`price`, value=`iron ingot`, "
            "op=`under`, threshold=`2.5`)."
        )
    lines = [f"**Trade watchers** — {len(watchers)} active", ""]
    for w in watchers:
        lines.append(f"- `{w.id}` — {w.label} ({w.query.describe()})")
    return "\n".join(lines)


def evaluate_markdown(hits: list[WatcherHit]) -> str:
    """Feed + display summary across all watchers for an MCP text block."""
    if not hits:
        return "**Trade watchers** — none to evaluate. Create one first with `action=create`."
    total_feed = sum(len(h.feed) for h in hits)
    lines = [
        f"**Trade watchers** — {len(hits)} watched, {total_feed} new hit(s) since last check",
        "",
    ]
    for h in hits:
        w = h.watcher
        display = f"{len(h.matches)} matching now"
        if h.feed:
            display += f", {len(h.feed)} new"
        best = min(
            (m["unitPrice"] for m in h.matches if m.get("unitPrice") is not None),
            default=None,
        )
        if best is not None:
            display += f", cheapest unit {best:g}"
        lines.append(f"- `{w.id}` {w.label} — {display}")
    return "\n".join(lines)
