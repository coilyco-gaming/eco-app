# Trades ledger

Row-level trades surface reconstructed from the Eco action-log exporter. Where
the economy card (`get_eco_economy`) only consumes aggregate
time-series counters, the exporter ships **every individual trade** - the
ledger pulls those rows and renders who sold what to whom, for how much, where,
and when. Filed as [#6](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/6).

## Surfaces

- **`get_eco_trades` MCP tool** - `src/eco_mcp_app/trades.py` + `server.py` wiring. Returns a markdown summary + the structured `TradesLedger.to_dict()` JSON. Trades is a "just data" tool - it emits no MCP-app widget ([#87](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/87); the widget is scoped to the world/region view). Requires an admin API key server-side (`ECO_ADMIN_API_KEY`, SSM in the homelab deploy).
- **Trades ledger in the `/trade` SPA page** - `frontend/src/pages/Trade.tsx`, consuming `/preview/get_eco_trades.json`. The standalone `/trades` page was folded into the trade & store logistics surface in the [#90](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/90) IA cleanup (`/trades` now redirects to `/trade`), so the market price-intelligence view and the row-level ledger share one page and one `?q=` filter. Product UX lives here (the Jinja card is only the in-chat fragment). The row-level table and the top-buyers/sellers leaderboards render below the market overview; the per-item price-over-time chart comes from the market drill.

## Data source

`GET /api/v1/exporter/actions?actionName=CurrencyTrade` returns one CSV row per
trade. Cycle-13 columns::

    BankAccount, Currency, CurrencyAmount, NumberOfItems, BoughtOrSold,
    ShopOwner, Buyer, Seller, WorldObjectItem, ItemUsed, Citizen,
    ActionLocation, Count, Time

`BarterTrade` shares the endpoint (currency-free, item-for-item, empty this
cycle). Both are fetched; the ledger folds whatever columns each exposes.

## What the ledger computes

- **Row-level trades** - newest first, capped at `ECO_TRADES_LEDGER_ROWS` (default 4000) for the shipped payload while the aggregates cover every parsed row.
- **Top buyers / sellers** - currency spent (by `Buyer`) and earned (by `Seller`).
- **Per-currency volume** and **most-traded items** (count + currency volume).
- **Price-over-time** - unit price = `CurrencyAmount / NumberOfItems`, mean per in-game day, for the busiest items. Rendered as an inline SVG line on `/trade`. This "falls out almost for free" once the rows are parsed.

## Messy bits handled (the pull-everything cleanups from the issue)

- **Numeric party ids** - `Buyer` / `Seller` / `ShopOwner` / `Citizen` are numeric in-game ids. Joined to names via the jobs mod's `/api/v1/citizens` surface (shared `crafting.fetch_citizen_name_map`), falling back to `Citizen #<id>` when a name is missing. The id→name link is [#5](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/5).
- **`BoughtOrSold` enum** - live values 32 / 33, undecoded in the exporter. Decoded best-effort to buy/sell (`BOUGHT_OR_SOLD`); the Eco `GameActions` source wasn't reachable from the build container to confirm polarity, so this is a heuristic. It only labels a secondary "direction" chip - the authoritative buyer/seller comes from the `Buyer` / `Seller` columns - so a wrong decode never corrupts a ledger row.
- **Time semantics** - integer seconds since cycle start, same convention as the species population CSV: in-game day = `Time / 86400` (`SECONDS_PER_DAY`).
- **Misalignment risk** - some exporter rows carry an undeclared extra tool column that shifts every later field. The ledger reuses `crafting._corrected_index` (scores candidate insertion points against per-column value shapes) so header-keyed picks stay aligned, and drops position-triple / bare-number values where a name belongs. Same defensive posture as the crafting CSVs ([#5](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/5)).

## Streaming & caching

CurrencyTrade grows without bound late-cycle, so the ledger stream-parses via
`crafting._stream_csv_rows` + a batched fold (never buffering the whole body),
capped at `ECO_TRADES_MAX_ROWS` per action. Results are cached in an in-process
`TTLCache` keyed per (base URL, api-key hash), TTL `ECO_TRADES_CACHE_TTL`
(default 60s), mirroring `server._economy_cache`.

## Follow-ups

- Confirm the `BoughtOrSold` 32/33 → buy/sell polarity against Eco's `GameActions` source when it's reachable, and check whether each trade logs one row or two (a buy-leg + sell-leg); if two, the row count and gross currency volume are per-leg, not per-trade.
