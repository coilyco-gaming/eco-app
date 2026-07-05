# eco-app features

Living inventory of what ships from this monorepo. Component-level detail lives in the per-component docs linked below, which were carried over from the four source repos during the consolidation ([coilysiren/inbox#101](https://forgejo.coilysiren.me/coilysiren/inbox/issues/101)).

## The fused service

One image, one uvicorn process, entrypoint `eco_mcp_app.http_app:app` on port 4000.

- **MCP server** - `src/eco_mcp_app/`, the core. Stdio for Claude Desktop, Streamable-HTTP at `/mcp/` for URL-connected hosts. Each tool returns text + structured JSON, plus an `_meta.ui` Jinja card for MCP Apps hosts (the only HTML the server renders). The `/preview/*.json` endpoints expose those tool payloads as the SPA's data plane. The `initialize` response advertises the Eco game icon (a 48x48 PNG data URI) as `serverInfo.icons`, so URL-connected hosts like claude.ai render the Eco globe on the connector tile instead of a generic placeholder. Full tool/resource inventory: [docs/mcp/FEATURES.md](mcp/FEATURES.md).
- **React frontend** - `frontend/`, a Vite + React + TypeScript SPA (no SSR). The Docker image builds it in a node stage and the fused service serves it at `/` (assets under `/assets`); a checkout without a build serves the JSON/MCP APIs only and returns a build hint for HTML routes (there is no server-rendered HTML surface - the old `/preview` card pages were removed, product UX is the SPA). The site is one flat surface ([#2](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/2)): the homepage is a thin directory of subpages (Server, Jobs, Economy, Trades, Crafting, Climate, Calculator, Community) with small live badges. `/economy` (KPI grid + health narrative), `/trades` (row-level trades ledger - who sold what to whom for how much, per-item price-over-time chart, top buyers/sellers, `?q=` deep links, filter-on-click), `/crafting` (ranked items/stations + top crafters by citizen, `?q=` deep links, filter-on-click), and `/climate` (atmosphere KPIs, CO2 source/sink breakdown, CO2-effects mechanic driven by the live per-server climate ruleset read from the telemetry mod's `/api/v1/climate-settings` endpoint - falling back to documented Eco defaults when that endpoint is absent - and a plain-language pollution-machine-style explainer that spells out CO2, ground pollution, and sea-level consequences) cross-link each other and consume the `/preview/*.json` data endpoints, and `/server` carries the live world snapshot from `/preview.json` (meteor countdown, players, world stats, 60s poll, graceful degraded state). A catch-all in `http_app.py` serves the SPA shell for client routes so hard refreshes survive. Scaffolding: react-router, eslint + vitest with component tests, run in CI. Dev verbs: `frontend-install` / `frontend-dev` / `frontend-build` / `frontend-test` / `frontend-lint`.
- **Jobs API** - `src/eco_spec_tracker/`, mounted at `/jobs/api` (public paths `/jobs/api/v1/*` plus `/v1/meta` for the mock-data flag). The jobs UI is the SPA's `/jobs` route consuming this API. Detail: [docs/jobs/FEATURES.md](jobs/FEATURES.md).
- **Calculator** - the SPA's `/calculator` route (`frontend/src/pages/Calculator.tsx`), the eco-app home for **Eco Gnome** (MIT), a price calculator that derives optimal buy/sell prices from a player's professions and recipes. Today it links out to the Eco-Gnome team's public instance with the MIT attribution preserved. The plan ([#40](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/40)) is to self-host the MIT tool on `eco-app.coilysiren.me` and feed it Sirens' modded recipes/skills/items via the DataExporter mod, so the pricing is server-accurate rather than vanilla. Because upstream is a Blazor Server + Postgres service (not WASM), the self-host is a deploy-repo slot, not a static bake into the fused image. Design of record: [docs/calculator.md](calculator.md).
- **Sentry telemetry** - one shared idempotent init (`eco_mcp_app/telemetry.py`), DSN via the `SENTRY_DSN` env var from the deploy repo's ExternalSecret.
- **Dev target resolver** - `scripts/resolve-eco-target.sh`, run by the `http` verb to pick the eco game server base URL: LAN mDNS path first (the home router blackholes same-LAN tailnet WireGuard, [infrastructure#294](https://forgejo.coilysiren.me/coilyco-flight-deck/infrastructure/issues/294)), then the SSM-resolved tailnet FQDN, then the public host. An explicit `ECO_INFO_URL` wins outright; `ECO_ADMIN_BASE_URL` / `ECO_MAP_BASE_URL` / `UPSTREAM_URL` (jobs skills endpoint) default to the same base, and `UPSTREAM_API_KEY` is SSM-resolved so local `/jobs` shows real player data, not the mock fallback.

## Local-only components

- **Replay browser** - `src/eco_replay/`, a FastAPI viewer for the replay mod's SQLite event log. Not mounted into the fused service yet. Detail: [docs/replay/README.md](replay/README.md).

## In-game C# plugins (`mods/`)

Server plugins for the Eco game server. Built with the `build-mod-*` ward verbs, shipped to the server out of band.

- **mods/jobs** - skills API plugin (`/api/v1/skills` for the jobs tracker, `/api/v1/citizens` for the crafting atlas's id→name join) plus a C# shell harness mirroring the API shape for local dev.
- **mods/replay** - player-action recorder writing the SQLite event log the replay browser reads. Action bodies are serialized with a structurally-bounded snapshot (allow-listed scalar props, wide references collapsed to `<name>`/`<n items>` summaries, 16 KB hard cap) and SQLite writes run on a background bounded-channel batched writer, never the game thread. Serializer unit tests: `ward exec test-mod-replay`.
- **mods/telemetry** - logs, exception capture, Eco game + runtime metrics, and OTLP traces (plugin-init spans plus a slow-handler detector) inside the game server. Detail: [mods/telemetry/docs/FEATURES.md](../mods/telemetry/docs/FEATURES.md).
- **mods/stores** - live store-offer exporter (`/api/v1/stores`): walks every live `StoreComponent` and emits each shelf's current offers (item, buy/sell, price, stock, currency, owner, location) so the store-directory, logistics-engine, and watcher siblings move from history-derived to shelf-accurate `Trades <item>` parity. Reflection-based, null-tolerant walk (survives orphaned stores and removed items), plus a C# shell harness mirroring the API shape for local dev. DTO contract: [mods/stores/docs/dto.md](../mods/stores/docs/dto.md).

## Build and release

- **CI** - `.forgejo/workflows/build-publish.yml`: pytest + ruff + mypy, then docker build and push of `coilysiren-eco-app` to the in-cluster registry. No deploy stage by design.
- **Deploy surface** - lives in `coilyco-bridge/deploy/services/eco-app` (manifests + rollout), per the layer invariant.

## Dropped during consolidation

- The 20M `species_profiles.json` + `ecopedia.json` offline caches, their build scripts, and the `_preload.py` lookup layer that fronted them ([#1](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/1)). Species/ecopedia lookups go straight to the live Wikidata/iNaturalist/Wikipedia paths in `species.py` / `wikidata.py`.
- The per-repo deploy stages and `deploy/main.yml` manifests (moved to the deploy repo, merged to one namespace).

## Data surfaces

- **Dataset survey + probe how-to** - [docs/datasets/](datasets/README.md): every populated dataset on the live server (192/205, cycle-13 capture) split per theme, plus the full fresh-session recipe for probing series (`/datasets/get`), action CSVs (`/api/v1/exporter/actions`), auth, time semantics, and known traps. Umbrella tracker: [#7](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/7).
- **Trades ledger** - [docs/trades.md](trades.md): the `get_eco_trades` tool and `/trades` page reconstruct a row-level trades surface from the `CurrencyTrade` / `BarterTrade` action CSVs - every individual trade with parties, item, quantity, currency amount, and in-game day, plus the aggregates that fall out (top buyers/sellers, per-currency volume, most-traded items, per-item price-over-time). Shares the crafting atlas's defensive-parse and id→name-join machinery ([#6](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/6)).
- **Market price intelligence** - the `get_eco_market` tool and `/preview/market.json` plane fold the trades ledger into a per-item, per-currency price series: median / min / max / units-traded per in-game day, plus a short-vs-long-window trend verdict (rising / falling / flat, or "insufficient" when data is too thin). Consumes the [#6](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/6) row model rather than re-parsing. The in-game median also wires back into the `fair_price` advisor, which now cross-references it against the real-world FRED benchmark ("in-game median X vs real-world trend Y → looks over/under/fair"), degrading to the FRED-only narrative when an item has no in-game trades. Exceeds DiscordLink's single asking price with history, volume, and a real-world anchor ([#49](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/49)).
- **Store & trader directory** - the `get_eco_stores` tool and `/preview/stores.json` data plane fold the same trade history into two directories: **store profiles** keyed by shop owner + location (items traded, buy-vs-sell mix, price points, volume, unique counterparties, last-trade recency) and **trader profiles** per citizen (buys, sells, top items, volume, stores operated). Meets DiscordLink's `Trades <player>` / `Trades <store>` from history and **exceeds** it by surfacing the **store owner** it omits, plus per-store/per-trader volume and recency. The buy/sell split is read structurally off the party columns, not the undecoded `BoughtOrSold` enum, and owner/party ids resolve to names via the citizens surface (`Citizen #<id>` fallback). History-only - the live shelf snapshot is the reset-gated **mods/stores** exporter above ([#50](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/50), under the DiscordLink-replacement epic [#37](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/37)).

## See also

- [README.md](../README.md) - human-facing intro.
- [AGENTS.md](../AGENTS.md) - agent-facing operating rules.
- [.ward/ward.yaml](../.ward/ward.yaml) - allowlisted commands.

Cross-reference convention from [coilysiren/agentic-os#59](https://github.com/coilyco-flight-deck/agentic-os/issues/59).
