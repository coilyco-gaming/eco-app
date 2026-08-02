# eco-mcp-app features

Baseline inventory of headline features. Use to evaluate scope changes.

## What this app is

MCP server exposing live data from Eco game servers. Production: `https://eco-mcp.coilysiren.me/mcp/`. Every tool returns markdown/text plus structured JSON; MCP Apps resources, widgets, and server-rendered cards were removed in [#113](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/113).

## MCP tools

Defined in [src/eco_mcp_app/server.py](../../src/eco_mcp_app/server.py) and the Wave 1 dual-route registry. Names are scoped to this MCP server and therefore omit a redundant Eco product prefix. Most accept an optional `server` argument, with each advertised input schema remaining authoritative. All return data-only results.

- **get_server_status** - Meteor countdown, players, world dims, cycle progress, version, economy summary.
- **get_economy** - Trades/day, contract completion, loan defaults, wages, tax flow, volatility sparklines. Admin `/datasets/get`.
- **get_map** - World map with property deeds. Translucent polygons, owner colors, Deck.gl WebGL.
- **get_milestones** - Culture achievement tracker. Per-goal bars, server-wide culture.
- **get_species** - Species card. iNaturalist/Wikipedia taxonomy + in-game population chart.
- **explain_item** - Wikidata + Wikipedia lookup. Images, category facts. 7-day cache.
- **get_crafting_atlas** - Live crafting from action-log exporter. Top items, station util, leaderboard.
- **get_trades** - Detailed trade ledger with parties, items, stores, currencies, and price history.
- **get_stores** - Store and trader directories derived from trade history.
- **get_progression** - Server-wide profession and specialty progression history.
- **get_social** - Community activity from the `Play`, `FirstLogin`, and `ReputationTransfer` action exporters: play volume, recent arrivals, and a who-reps-whom reputation graph. `ChatSent` is deliberately not fetched or returned ([#185](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/185)). Player names are hashed to stable handles by default. Names in the clear remain operator-gated (`ECO_SOCIAL_ALLOW_NAMES` + `reveal_names`) and never reach the public JSON path.
- **get_world** - World / industry activity from the action-log exporter. Construction, terraforming, roads, moved objects, explosions, garbage, and air pollution folded into a per-day mutation timeline by category, a top-world-shapers + top-polluters leaderboard, most-touched objects, and coarse-binned activity hotspots. No new mod, no restart - reuses the crafting atlas's streamed-CSV plumbing. Probe: [docs/world.md](../world.md).
- **get_market** - Per-item and per-currency price history, volume, and trend intelligence.
- **find_trade** - Resale, arbitrage, and supply-gap decisions from history and live shelves.
- **fair_price** - Real-world commodity prices via FRED (copper, wheat, lumber, iron, crude). 7d/30d/90d.
- **get_region** - WWF ecoregion classification. Donut, top-3 matches, boom/bust lists.
- **get_government** - Civic org chart. Elected titles, active elections, active laws (current-state snapshot from the live civic endpoints).
- **get_civics** - Civics & governance history + trend from the civic action exporters (`Vote`/`DidntVote`/`StartElection`/`WonElection`/`BecomeCitizen`/`SettlementFounded`/…) plus civics/people daily series: elections started + outcomes, voter turnout (cast vs abstained, participation rate, most-active-voter leaderboard), demographic movement (citizens gained/lost, residency moves), settlements founded + homesteads. Acting citizens resolved to names via the citizens surface (`Citizen #<id>` fallback). The website-and-MCP answer to DiscordLink's elections/votes/demographics displays, exceeding them with turnout + demographic trend over time; complements `get_government` (laws-in-effect aren't derivable from the action stream). Probe: [docs/civics.md](../civics.md).
- **get_climate** - CO2 ppm, sea-level + drift, ground pollution, avg temperature, NOAA Mauna Loa anchor, top polluters. Plus a pollution-machine-style explainer: CO2 sources & sinks breakdown (pollution/animals/plants, lifetime + per-day), the CO2-effects mechanic (warming + sea-level thresholds), and a plain-language "what to expect" narration. Tolerant to dataset-name drift.
- **get_currency** - Currency & money-supply surface, meets DiscordLink `Currencies` / `Currency <name>`. Roster split minted/backed vs personal/credit (each with issuance + trade activity), money-supply totals (player wealth + gov holdings) and 7d trade value. Optional `currency` arg gives the per-currency report, including the live top account holders (per-account balances from the `mods/stores` `/api/v1/currency-holdings` exporter, joined to citizen names; flagged unavailable rather than faked when that mod is not deployed - [#58](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/58)). Roster + issuance from the `CreateCurrency` / `MintCurrency` / `CurrencyTrade` action exporters, supply from `/datasets/get`; degrades to the public `/info` headline without an admin key. Probe: [docs/datasets/currency.md](../datasets/currency.md).
- **trade_watchers** - Persistent create, list, remove, and evaluate operations for item, store, trader, and price predicates.
- **list_public_servers** - 6 known public servers with labels + notes.

## Runtime surfaces

- **Stdio** - `python -m eco_mcp_app.__main__` for Claude Desktop.
- **HTTP** - MCP over Streamable-HTTP at `POST /mcp/`. Stateless.
- **Health probe** - `GET /healthz`.
- **Data plane** - `GET /preview.json`, `/preview-map.json`, `/preview/currency.json`, `/preview/<tool>.json` return tool payloads as JSON for the SPA to consume. `/preview/currency.json` is a dedicated short path (passing `?server=` / `?currency=` through) for the `/trade` SPA route; the rest dispatch any tool by name. No HTML variant - the dev `/preview` card pages were removed.
- **Livereload WS** - Debug-mode hot reload.

## UI rendering

The React SPA (`frontend/`) is the product UI. The MCP service renders no HTML and registers no UI resources.

## External data sources

- **Eco public `/info`** - Default `http://eco.coilysiren.me:3001/info`, override `ECO_INFO_URL`.
- **Eco admin `/datasets/get`** - Economic time-series. `ECO_ADMIN_API_KEY`.
- **Eco admin `/exporter/*`** - Action logs (crafting, harvesting, mining), species, deeds. CSV stream-parsed.
- **Wikidata + Wikipedia** - Item taxonomy + images. 7-day TTL.
- **FRED** - Commodity prices. `FRED_API_KEY`.
- **iNaturalist** - Species taxonomy + images. Wikipedia fallback.

## Bundled data assets

- **data/ecoregions.json** (~7KB) - WWF ecoregion defs. The former ecopedia/species blobs were dropped during consolidation - lookups go live.

## Source modules

- **server.py** - Core MCP server and tool handlers.
- **http_app.py** - Starlette ASGI + NormalizeMcpPath middleware.
- **crafting.py** / **map.py** / **ecoregion.py** / **species.py** / **fair_price.py** / **wikidata.py** / **telemetry.py** / **livereload.py**.

## Deployment

- **Docker image** - Alpine Python 3.13 + uv. `ghcr.io/coilysiren/eco-mcp-app/coilysiren-eco-mcp-app:latest`.
- **k8s manifest** - Namespace, Deployment, Service, Ingress, ExternalSecrets (GHCR pull-secret, FRED key, Eco admin token from SSM).
- **Tailscale + cert-manager** - Encrypted cluster access from GHA, auto TLS.
- **CI/CD** - GHA builds, pushes GHCR, deploys via kubectl over Tailscale. Trufflehog secret scan.
- **Public endpoint** - `https://eco-mcp.coilysiren.me/mcp/`. Local default port 4000.

## Dev tooling

- **ward verbs** in [.ward/ward.yaml](../../.ward/ward.yaml), each delegating to Make.
  - `ward exec smoke` - Stdio initialization, discovery, and representative tool calls.
  - `ward exec http` - Local HTTP on 4000 with hot reload.
  - `ward exec harness` - Browser dev harness on `:8765`.
  - `ward exec install-desktop` - Auto-register in Claude Desktop config.
- **Pre-commit** - ruff + mypy.
- **Tests** - pytest, pytest-asyncio, respx.

## See also

- [README.md](../../README.md) - human-facing intro.
- [AGENTS.md](../../AGENTS.md) - agent-facing operating rules.
- [.ward/ward.yaml](../../.ward/ward.yaml) - allowlisted commands.

Cross-reference convention from [coilysiren/agentic-os#59](https://github.com/coilyco-flight-deck/agentic-os/issues/59).
