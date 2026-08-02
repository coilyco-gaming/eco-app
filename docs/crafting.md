# Crafting Activity Atlas

A live picture of production on the server, reconstructed from the Eco
action-log exporter. Where recipes-as-definitions are never exposed over HTTP,
the exporter ships **every production event** - so the atlas is built from
**observed events only**, which is strictly better: mod items (BunWulf, Nid) and
vanilla items all appear naturally wherever they are actually crafted, harvested,
or mined. Filed as [#17](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/17).

## Surfaces

- **`get_crafting_atlas` MCP tool** - `src/eco_mcp_app/crafting.py` + `server.py` wiring. Returns a markdown summary + the structured `CraftingAtlas.to_dict()` JSON. Requires an admin API key server-side (`ECO_ADMIN_API_KEY`, populated from SSM `/eco-mcp-app/api-admin-token` in the homelab deploy).
- **`/crafting` SPA page** - `frontend/src/pages/Crafting.tsx`, consuming `/preview/get_crafting_atlas.json` via `lib/craftingApi.ts`. Product UX lives here. Ranked items/stations feed a `?q=` filter with filter-on-click deep links; the top-crafters list and the sankey do not filter. Cross-links `/trade` and `/items` (the former `/economy` and `/trades` cross-links were repointed in the [#90](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/90) IA cleanup).

## Data sources

Four action exporters describe "production" in Eco, all pulled and folded into
one atlas:

    ItemCraftedAction     bench crafts        (WorldObjectItem, Citizen, ItemUsed, Count)
    HarvestOrHunt         plant/animal        (Species is the produced stack)
    ChopTree              forestry            (Species is the felled tree)
    DigOrMine             excavation          (BlockItemOnDestroy / ItemUsed)

`GET /api/v1/exporter/actions?actionName=<name>` returns CSV, one row per event.
`GET /api/v1/exporter/actionlist` is the newline-delimited (**not** JSON) catalog
of available action names. The exporter exposes no date/time-range query param to
cap input server-side, so aggregation happens client-side in a single streaming
pass (see below). A disabled or erroring action endpoint is a non-fatal warning -
partial data is still useful; a `0`-count entry distinguishes "fetched, empty"
from "never fetched".

## What the atlas computes

- **Top items crafted** - `Count` summed by output item, `ItemCraftedAction` only. This is a real unit count ("how many were made"). Top 20 on the MCP card, top 25 on the SPA.
- **Top resources gathered** - `HarvestOrHunt` / `ChopTree` / `DigOrMine` output (`Species` for harvests/chops, the block for mining), counted by **event**, not by `Count`. Their `Count` is a harvest *magnitude* (biomass / weight, hundreds-of-thousands per chop), so summing it across action types buried real crafting under plant biomass - the two boards are kept separate for exactly that reason ([#70](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/70)).
- **Crafting-station utilization** - event count per `WorldObjectItem` (Campfire, Workbench, Carpentry Table...), ranked hot to cold. Hand/tool-driven actions record the tool or `(hand)`.
- **"Flows into what" sankey** - edges `WorldObjectItem -> output`, thickness = **event count** (event-weighted so a single 200k-biomass chop can't swamp the diagram - [#70](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/70)). Rendered as a **static server-side SVG** (see the deviation note below).
- **Per-citizen leaderboard** - top producers by total production **events** (crafts + gathers) across all four action types, so a plant harvester's biomass can't dominate ([#70](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/70)).

## Messy bits handled

- **Numeric citizen ids** - `Citizen` is a numeric in-game user id. Joined to display names via the jobs mod's `/api/v1/citizens` surface (`crafting.fetch_citizen_name_map`, shared with the trades ledger), falling back to `Citizen #<id>` when a name is missing. When nothing resolves, a "showing numeric ids" warning is surfaced rather than rendering silently-wrong labels. The id→name link is [#5](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/5).
- **Misalignment risk** - some exporter rows carry an undeclared extra tool column (e.g. `HandsItem`) that shifts every later field. `_corrected_index` recovers the shift by scoring each candidate insertion point against per-column value shapes (`_COLUMN_SHAPE`) and keeping the best fit; residual position-triple / bare-number values where a name belongs are dropped rather than rendered ([#5](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/5)).
- **Item-name prettifying** - `prettify_eco_name` turns `CampfireItem` -> `Campfire` and `BunWulfRawMeatItem` -> `Bun Wulf Raw Meat` heuristically (PascalCase `FooItem` convention), with no lookup table so it survives unknown mods. Citizen names are shown verbatim (already resolved), never prettified.

## Streaming & caching

`ItemCraftedAction` grows without bound late-cycle (~295 KB on day 3, 20+ MB by
meteor), so the atlas stream-parses via `_stream_csv_rows` (`httpx.AsyncClient.stream`
+ `csv.reader` on a bounded line buffer) and folds in batches, never materializing
the whole body. A per-action `MAX_ROWS_PER_ACTION` cap (default 500k, ~50 MB of CSV)
is a defensive valve for pathological late-cycle sizes; hitting it appends a
truncation warning. `test_fetch_atlas_large_stream_stays_bounded` feeds a synthetic
~24 MB stream to prove peak memory stays sane. Results are cached in a SQLite file
under `~/.cache/eco-mcp-app/crafting.sqlite` (`ECO_CACHE_DIR` overridable), keyed
per (base URL, api-key hash) so swapping servers never cross-contaminates, TTL
`ECO_CRAFTING_CACHE_TTL` (default 300s).

## Deviation from the issue: sankey rendering

The issue specified `d3-sankey` bundled into the HTML (CSP forbids a runtime CDN
load). The shipped card instead renders a **static two-column SVG sankey computed
server-side** (`_build_sankey_layout`). The layout is computed once and never
re-laid-out interactively, so ~20 KB of bundled d3 buys nothing here; a static SVG
satisfies CSP trivially with zero JS, is easier to inspect in tests, and sorts both
axes by total flow which keeps crossings minimal for this bipartite shape. Same
outcome as the issue's acceptance check ("no more than 5 crossings"), less weight.

## Follow-ups

- If the exporter ever grows a date/time-range query param, use it to cap input server-side instead of the client-side row valve.
- The sankey caps at the top 30 flow edges; a very wide production graph late-cycle could hide long-tail stations. Revisit the cap (or add an on-card "N more flows" note) if that shows up in a full cycle's data.
