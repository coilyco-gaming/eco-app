# eco-mcp-app features

Baseline inventory of headline features. Use to evaluate scope changes.

## What this app is

MCP server exposing live data from Eco game servers as Claude Desktop widget cards. Reference implementation of MCP Apps spec in pure Python (no React, no bundler). Production: `https://eco-mcp.coilysiren.me/mcp/`.

## MCP tools

Defined in [src/eco_mcp_app/server.py](../../src/eco_mcp_app/server.py). All accept optional `server` arg.

- **get_eco_server_status** - Meteor countdown, players, world dims, cycle progress, version, economy summary.
- **get_eco_economy** - Trades/day, contract completion, loan defaults, wages, tax flow, volatility sparklines. Admin `/datasets/get`.
- **get_eco_map** - World map with property deeds. Translucent polygons, owner colors, Deck.gl WebGL.
- **get_eco_milestones** - Culture achievement tracker. Per-goal bars, server-wide culture.
- **get_eco_species** - Species card. iNaturalist/Wikipedia taxonomy + in-game population chart.
- **explain_eco_item** - Wikidata + Wikipedia lookup. Images, category facts. 7-day cache.
- **get_eco_crafting_atlas** - Live crafting from action-log exporter. Top items, station util, leaderboard.
- **get_eco_social** - Social / chat surface from the `ChatSent` / `Play` / `FirstLogin` / `ReputationTransfer` action exporters: activity timeline, chat volume by day + channel, a who-reps-whom reputation graph, and redacted recent-chat samples. Player names hashed to handles and message bodies name-scrubbed **by default** (chat is player-authored); names-in-the-clear is operator-gated (`ECO_SOCIAL_ALLOW_NAMES` + `reveal_names`), never public.
- **get_eco_world** - World / industry activity from the action-log exporter. Construction, terraforming, roads, moved objects, explosions, garbage, and air pollution folded into a per-day mutation timeline by category, a top-world-shapers + top-polluters leaderboard, most-touched objects, and coarse-binned activity hotspots. No new mod, no restart - reuses the crafting atlas's streamed-CSV plumbing. Probe: [docs/world.md](../world.md).
- **fair_price** - Real-world commodity prices via FRED (copper, wheat, lumber, iron, crude). 7d/30d/90d.
- **get_eco_ecoregion** - WWF ecoregion classification. Donut, top-3 matches, boom/bust lists.
- **get_eco_government** - Civic org chart. Elected titles, active elections, active laws.
- **get_eco_climate** - CO2 ppm, sea-level + drift, ground pollution, avg temperature, NOAA Mauna Loa anchor, top polluters. Plus a pollution-machine-style explainer: CO2 sources & sinks breakdown (pollution/animals/plants, lifetime + per-day), the CO2-effects mechanic (warming + sea-level thresholds), and a plain-language "what to expect" narration. Tolerant to dataset-name drift.
- **get_eco_currency** - Currency & money-supply surface, meets DiscordLink `Currencies` / `Currency <name>`. Roster split minted/backed vs personal/credit (each with issuance + trade activity), money-supply totals (player wealth + gov holdings) and 7d trade value. Optional `currency` arg gives the per-currency report. Roster + issuance from the `CreateCurrency` / `MintCurrency` / `CurrencyTrade` action exporters, supply from `/datasets/get`; degrades to the public `/info` headline without an admin key. Top holders are deferred (no per-account-balance export surface) and flagged, not faked. Probe: [docs/datasets/currency.md](../datasets/currency.md).
- **list_public_eco_servers** - 6 known public servers with labels + notes.

## MCP resources

- **ui://eco/status.html** - Main MCP Apps shell document hosts load in their sandboxed iframe; per-tool Jinja cards swap into it via `_meta.ui.fragment`.
- **ui://eco/economy.html** - Economy dashboard shell.
- **ui://eco/climate.html** - Climate dashboard shell.
- **ui://eco/currency.html** - Currency & money-supply dashboard shell.

## Runtime surfaces

- **Stdio** - `python -m eco_mcp_app.__main__` for Claude Desktop.
- **HTTP** - MCP over Streamable-HTTP at `POST /mcp/`. Stateless.
- **Health probe** - `GET /healthz`.
- **Data plane** - `GET /preview.json`, `/preview-map.json`, `/preview/currency.json`, `/preview/<tool>.json` return tool payloads as JSON for the SPA to consume. `/preview/currency.json` is a dedicated short path (passing `?server=` / `?currency=` through) for the `/trade` SPA route; the rest dispatch any tool by name. No HTML variant - the dev `/preview` card pages were removed.
- **Livereload WS** - Debug-mode hot reload.

## UI rendering

- **Jinja2 server-side** at [src/eco_mcp_app/templates/](../../src/eco_mcp_app/templates/), rendered only into the MCP `_meta.ui` card fragment for in-chat hosts. The web UI is the React SPA (`frontend/`); the server renders no browser-facing HTML.
- **Main shell** `eco.html` (~5KB). Hand-rolled MCP Apps handshake. Steam banner data URI for CSP.
- **CSS** `eco.css` (~26KB). Responsive, animated starfield, cycle ring.
- **22 partial templates** for per-card fragments.
- **Connector icon** - the `initialize` metadata carries the official Eco game icon (48x48 PNG data URI, the blue/green world globe) as `serverInfo.icons`, so claude.ai and other URL-connected hosts brand the connector tile with the game icon. Asset: `templates/assets/eco_icon.png`.

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

- **server.py** - Core MCP server, tool/resource handlers, TMP markup parsing, error rendering. ~2400 lines.
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
  - `ward exec smoke` - Stdio test of all 12 tools.
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
