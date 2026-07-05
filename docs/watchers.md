# Trade watchers

Host-agnostic trade watchers - the website-and-MCP answer to DiscordLink's
trade-watch commands, with no Discord dependency. DiscordLink ships
`WatchTradeFeed` (an event stream to a Discord DM), `WatchTradeDisplay` (a
self-updating snapshot), plus `UnwatchTradeFeed/Display` and `ListTradeWatchers`.
The epic thesis ([#37](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/37))
is that this read-only info belongs on **the website**, not a Discord DM. This
subsystem **meets** those verbs and **exceeds** them: it delivers to the SPA and
MCP instead of a DM, and adds a numeric price predicate, not just a name match.
Filed as [#52](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/52).

## No-reset spine

Watchers evaluate against the `CurrencyTrade` / `BarterTrade` history the server
**already exports** (see [docs/trades.md](trades.md)). Each evaluation diffs the
newest trades against the stored watch queries - no new C# mod, no server reset.
The two DiscordLink semantics both fall out of one pass over the ledger:

- **Feed** - matching trades with a `time` past the watcher's stored last-seen
  mark. The event-stream semantic: each matching trade is surfaced exactly once,
  then the mark advances past it.
- **Display** - the current matching state: how many trades match right now, the
  most recent handful, the cheapest unit price, total volume. The
  self-updating-snapshot semantic. It never consumes the feed mark.

## Query kinds

- **`item`** - match a trade's item, by raw Eco name (`IronIngotItem`) or its
  prettified form (`iron ingot`). Case-insensitive substring.
- **`store`** - match the store (`WorldObjectItem`) the trade happened at.
- **`trader`** - match any party (buyer, seller, or shop owner) by resolved name.
- **`price`** - an item plus a threshold predicate on unit price, e.g. "iron
  ingot under 2.5". Needs `op` (`under` / `over`) and `threshold`. This is the
  exceeds-DiscordLink predicate. A barter or unpriced row never matches a price
  watcher.

## Surfaces

- **`eco_trade_watchers` MCP tool** - `src/eco_mcp_app/watchers.py` +
  `server.py` wiring. One tool, four verbs via the `action` argument:
  - `create` - `kind` + `value`; for `kind=price` also `op` + `threshold`.
    Optional `label`, `server`.
  - `list` - every stored watcher.
  - `remove` - delete by `id`.
  - `evaluate` - run all watchers against the live ledger. `advance` defaults
    true (the feed semantic - consumes each feed hit); pass false to peek.
    Needs an admin API key server-side (`ECO_ADMIN_API_KEY`, SSM in the homelab
    deploy) to reach the exporter, same as `get_eco_trades`.
  Each verb returns a markdown summary plus a structured JSON block.
- **`/trades` SPA sidebar** - `frontend/src/pages/Trades.tsx` consuming
  `/preview/watchers.json`. The endpoint evaluates in **peek** mode
  (`advance=false`), so loading the page shows each watcher's current matching
  state and a "+N new" feed badge without consuming the feed - only the MCP
  `evaluate` verb advances the marks. The sidebar is read-only: watchers are
  created and removed over MCP.

## Persistence

A small SQLite store at `~/.cache/eco-mcp-app/watchers.sqlite`, mirroring the
fair-price cache pattern (`fair_price.default_cache_dir()`, so
`ECO_MCP_CACHE_DIR` relocates both). One row per watcher, keyed by id, carrying
the query (`kind`, `value`, `op`, `threshold`), the `last_seen` timestamp, the
`label`, an optional `server`, and the `created_at` time. The schema is created
idempotently on first open and survives a process restart.

`last_seen` starts at 0, so a fresh watcher's first evaluation treats every
current match as a feed hit (feed and display agree on the first poll); the mark
then advances to the newest matching trade's `time` so each feed hit is surfaced
exactly once.

## Tests

`tests/mcp/test_watchers.py` (respx-mocked) covers query validation, match logic
for every kind, the feed-vs-display split, the last-seen advance (a second
evaluation of the same ledger surfaces no fresh feed hits; peek mode never
consumes), SQLite create/list/remove, the MCP tool wiring, and the
`/preview/watchers.json` endpoint. `frontend/src/pages/Trades.test.tsx` covers
the SPA sidebar. Both run under `ward exec test` / `ward exec frontend-test`.
