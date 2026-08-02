# Dual REST and MCP route inventory

This document classifies the routes owned by the fused eco-app service for
adoption by the shared [`DualRouteRegistry`](../src/eco_mcp_app/dual_routes.py).
It records the baseline and migration state as production routes move into the
registry. The tracking issue is [eco-app#205](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/205),
with Wave 1 implemented in [eco-app#207](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/207).
Wave 2 is implemented in [eco-app#209](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/209).

## Scope

The inventory covers the public MCP server, the privileged admin MCP, the
top-level Starlette app, the mounted Jobs and Replay FastAPI apps, and the React
router. The owning sources are
[`server.py`](../src/eco_mcp_app/server.py),
[`admin/server.py`](../src/eco_mcp_app/admin/server.py),
[`http_app.py`](../src/eco_mcp_app/http_app.py),
[`eco_spec_tracker/main.py`](../src/eco_spec_tracker/main.py),
[`eco_replay/main.py`](../src/eco_replay/main.py), and
[`frontend/src/App.tsx`](../frontend/src/App.tsx).

The in-game C# mod endpoints and external Eco server endpoints are upstream
dependencies, not routes owned by the fused service. They are outside this
registry. MCP transport paths, static files, probes, authentication helpers,
and browser navigation are routes, but they are not domain operations and do
not belong in a REST/MCP operation registry.

## Classification rules

* **Dual-register** - The REST endpoint and MCP tool perform the same domain operation with the same input, output, authorization, disclosure, side effects, and error semantics. The operation has bounded structured output and a useful model-facing purpose.
* **Dual-register after prerequisite** - A shared operation is useful, but its current contract needs typed models, result bounds, transport-safe input projection, or a read-only split before registration.
* **Single-surface** - The route is intentionally REST-only, MCP-only, or browser-only because the other transport has no matching use case.
* **Excluded** - The route is transport plumbing, privileged infrastructure, or has disclosure or mutation semantics that must not be expanded by the public registry.

A shared registration must own one Pydantic input model, one Pydantic output
model, one domain handler, the MCP title and description, and the canonical
REST method and path. Compatibility aliases may call the same domain handler,
but an alias that changes output detail, disclosure, or side effects remains a
separate transport adapter.

## Current registry state

`create_app()` and `build_server()` accept the same registry. The production
registry automatically registers the twenty Wave 1 and Wave 2 read-only
operations listed below, including typed input and output schemas, shared
success and error payloads, and canonical REST methods and paths. The existing
`GET /preview/{tool}` adapter remains a compatibility route for the two public
MCP tools with transport-specific semantics. It has no per-operation schemas,
safe HTTP method selection, typed outputs, or transport-specific disclosure
controls.

## Public MCP operations

The public server currently exposes 22 tools. Twenty are read-only operations
whose HTTP and MCP forms can converge on one shared registration.

* `get_server_status` - **Registered in Wave 1** - Canonical REST path `GET /preview.json`.
* `get_economy` - **Registered in Wave 2** - Canonical REST path `GET /preview/get_economy.json`.
* `get_map` - **Registered in Wave 2** - Canonical exact REST path `GET /preview/get_map.json`. The richer `GET /preview-map.json` projection stays separate because it adds biome rasters that the MCP result omits.
* `get_milestones` - **Registered in Wave 2** - Canonical REST path `GET /preview/get_milestones.json`.
* `get_species` - **Registered in Wave 2** - Canonical REST path `GET /preview/get_species.json`, with required `name` input.
* `explain_item` - **Registered in Wave 2** - Canonical REST path `GET /preview/explain_item.json`, with required `name` and optional constrained `category`.
* `get_crafting_atlas` - **Registered in Wave 2** - Canonical REST path `GET /preview/get_crafting_atlas.json`.
* `get_world` - **Registered in Wave 1** - Canonical REST path `GET /preview/world.json`.
* `get_trades` - **Registered in Wave 2** - Canonical REST path `GET /preview/get_trades.json`.
* `get_stores` - **Registered in Wave 1** - Canonical REST path `GET /preview/stores.json`.
* `get_progression` - **Registered in Wave 1** - Canonical REST path `GET /preview/progression.json`.
* `fair_price` - **Registered in Wave 2** - Canonical REST path `GET /preview/fair_price.json`, with required `item` and optional `cycle_id` and `server`.
* `get_market` - **Registered in Wave 1** - Canonical REST path `GET /preview/market.json`.
* `find_trade` - **Registered in Wave 1** - Canonical REST path `GET /preview/logistics.json`.
* `get_region` - **Registered in Wave 2** - Canonical REST path `GET /preview/get_region.json`.
* `get_climate` - **Registered in Wave 2** - Canonical REST path `GET /preview/get_climate.json`.
* `get_currency` - **Registered in Wave 1** - Canonical REST path `GET /preview/currency.json`.
* `get_government` - **Registered in Wave 2** - Canonical REST path `GET /preview/get_government.json`.
* `get_civics` - **Registered in Wave 1** - Canonical REST path `GET /preview/civics.json`.
* `list_public_servers` - **Registered in Wave 1** - Canonical REST path `GET /preview/list_public_eco_servers.json`.
* `get_social` - **Dual-register after prerequisite** - The dedicated `GET /preview/social.json` path always suppresses `reveal_names`, while MCP may accept it behind `ECO_SOCIAL_ALLOW_NAMES`. Add a REST input projection or split the operator disclosure capability before registration. Do not expose `reveal_names` through the public REST schema.
* `trade_watchers` - **Dual-register after prerequisite** - The MCP tool multiplexes create, list, remove, and state-advancing evaluate actions. `GET /preview/watchers.json` hard-codes read-only evaluate with `advance=false`. Keep mutations MCP-only and define a separate read-only peek operation before sharing a GET route.

## Top-level HTTP routes

The public app now materializes 35 method-path pairs before its mounts and
optional debug/static routes. Twenty come from the shared registry and the rest
remain explicit Starlette declarations. The preview routes below are the
domain-facing subset.

* `GET /preview.json` - **Registered in Wave 1** - Shared with `get_server_status`.
* `GET /preview/get_economy.json` - **Registered in Wave 2** - Shared with `get_economy`.
* `GET /preview/get_map.json` - **Registered in Wave 2** - Shared with `get_map`.
* `GET /preview-map.json` - **Single-surface REST projection** - Includes browser-only biome raster detail. It may reuse map domain logic, but it must not replace the smaller shared operation.
* `GET /preview/get_milestones.json` - **Registered in Wave 2** - Shared with `get_milestones`.
* `GET /preview/get_species.json` - **Registered in Wave 2** - Shared with `get_species`.
* `GET /preview/explain_item.json` - **Registered in Wave 2** - Shared with `explain_item`.
* `GET /preview/get_crafting_atlas.json` - **Registered in Wave 2** - Shared with `get_crafting_atlas`.
* `GET /preview/get_trades.json` - **Registered in Wave 2** - Shared with `get_trades`.
* `GET /preview/fair_price.json` - **Registered in Wave 2** - Shared with `fair_price`.
* `GET /preview/get_region.json` - **Registered in Wave 2** - Shared with `get_region`.
* `GET /preview/get_climate.json` - **Registered in Wave 2** - Shared with `get_climate`.
* `GET /preview/get_government.json` - **Registered in Wave 2** - Shared with `get_government`.
* `GET /preview/currency.json` - **Registered in Wave 1** - Shared with `get_currency`.
* `GET /preview/market.json` - **Registered in Wave 1** - Shared with `get_market`.
* `GET /preview/stores.json` - **Registered in Wave 1** - Shared with `get_stores`.
* `GET /preview/logistics.json` - **Registered in Wave 1** - Shared with `find_trade`.
* `GET /preview/civics.json` - **Registered in Wave 1** - Shared with `get_civics`.
* `GET /preview/progression.json` - **Registered in Wave 1** - Shared with `get_progression`.
* `GET /preview/social.json` - **Dual-register after prerequisite** - Public redaction is stricter than the MCP input surface.
* `GET /preview/world.json` - **Registered in Wave 1** - Shared with `get_world`.
* `GET /preview/watchers.json` - **Dual-register after prerequisite** - This is a read-only peek, not the same operation as the mutating MCP multiplexer.
* `GET /preview/user.json` - **Single-surface REST** - Hidden per-user dossier with identity-bearing data and a wide multi-source payload. Do not add it to public MCP without a separate disclosure and minimization design.
* `GET /preview/items.json` - **Dual-register after prerequisite** - The full item directory is useful to models but too broad as an unfiltered tool result. Define query, ordering, and maximum-result inputs first.
* `GET /preview/food.json` - **Dual-register after prerequisite** - Add a bounded `get_food_signals` operation with typed input and output models.
* `GET /preview/item.json` - **Dual-register after prerequisite** - Add a model-facing item-activity operation only after the event feed has explicit server-side limits or pagination.
* `GET /preview/price-history.json` - **Dual-register after prerequisite** - Add a typed `get_item_price_history` operation. Preserve the required item and currency pair and the current-cycle interpretation rules.
* `GET /preview/recipes.json` - **Single-surface REST** - The default 1,453-recipe graph and optional live cost overlay are a browser data plane. A future MCP operation should require a product, skill, station, or ingredient filter and enforce a result limit instead of sharing the full route.
* `GET /preview/{tool}` - **Excluded transition adapter** - It dynamically exposes MCP tools through query strings and JSON-block extraction. Keep it only as compatibility coverage while explicit registrations land, then remove it after every client path is audited.

The remaining top-level routes are not shared domain operations.

* `GET /api/service` - **Single-surface REST** - Service discovery for HTTP clients.
* `GET /healthz` - **Excluded probe** - Kubernetes health contract.
* `GET /page-auth` - **Excluded authentication helper** - Tells the SPA whether its soft password prompt is configured.
* `POST /page-auth` - **Excluded authentication helper** - Verifies the SPA password. It is not an MCP capability.
* `GET /` - **Excluded browser route** - Serves the SPA entry document or a local build hint.
* `/mcp/*` - **Excluded transport mount** - Streamable HTTP is the MCP protocol endpoint, not a domain route.
* `/admin/*` - **Excluded privileged transport mount** - Present only when `ECO_ADMIN_ENABLED` is set.
* `/assets/*` - **Excluded static mount** - Present when the frontend build contains assets.
* `/ws/livereload` - **Excluded debug transport** - Present only in debug mode.
* `GET /{path:path}` - **Excluded browser fallback** - Serves root-level static files or the SPA entry document for client-side routes.

## Mounted Jobs API

The Jobs app is mounted at `/jobs/api`. FastAPI also supplies its default
`/openapi.json`, `/docs`, `/docs/oauth2-redirect`, and `/redoc` routes beneath
that mount. Those generated documentation routes are **single-surface REST**
and stay outside the operation registry.

* `GET /jobs/api/v1/meta` - **Single-surface REST** - Fixture-state banner for the browser.
* `GET /jobs/api/v1/professions` - **Dual-register after prerequisite** - Extract a typed `get_professions` operation from the FastAPI response shaping.
* `GET /jobs/api/v1/specialties` - **Dual-register after prerequisite** - Add profession, specialty, active-status, and result-limit filters before exposing the roster to MCP.
* `GET /jobs/api/v1/players` - **Single-surface REST** - Broad identity-bearing roster. A future MCP operation needs a named coordination use case, disclosure review, and bounded filters.

## Mounted Replay API

The Replay app is mounted at `/replay/api`. Its generated OpenAPI and docs
routes follow the same FastAPI defaults and stay REST-only.

* `GET /replay/api/v1/meta` - **Single-surface REST** - Fixture-state banner for the browser.
* `GET /replay/api/v1/events` - **Single-surface REST** - The event timeline can contain citizen names and heterogeneous action bodies. Keep it out of public MCP until a minimized, disclosure-safe model operation is designed.
* `GET /replay/api/v1/events/stats` - **Single-surface REST** - Browser readiness and count metadata has no independent model-facing operation.

## Privileged admin MCP

The admin server exposes 14 MCP-only tools. Every one remains **excluded from
the public dual registry** because the feature flag, node-local mounts, RCON
credential, disclosure levels, and operator-only text rules form one security
boundary.

* Save and world - `admin_save_status`, `admin_backup_list`,
  `admin_world_meta`.
* Configs - `admin_config_get`, `admin_config_diff`,
  `admin_mod_configs`.
* Replay state - `admin_events_recent`, `admin_player_activity`.
* Logs - `admin_log_tail`, `admin_log_grep`.
* Mods - `admin_mods_installed`.
* Runtime - `admin_live_status`, `admin_service_health`.
* RCON - `admin_rcon_query`.

If an admin REST API is ever required, it needs a separate registry mounted
inside the existing admin feature flag and authorization boundary. Registering
admin operations in the public registry is not an acceptable shortcut.

## SPA routes

React navigation is browser state, not an operation surface. All current SPA
paths remain **excluded from the dual registry** and continue through the final
Starlette fallback.

* Active pages - `/`, `/info`, `/mods`, `/wiki`, `/jobs/*`, `/trade`, `/crafting`, `/items`, `/item`, `/recipes`, `/recipe`, `/civics`, `/uses`, `/uses/demand`, `/uses/food`, `/uses/buy-sell`, `/uses/arbitrage`, `/uses/price`, `/uses/resolve`, `/uses/shop-check`, `/social`, `/map`, `/species`, `/replay`, and `/users/:hex`.
* Compatibility redirects - `/server`, `/progression`, `/economy`, `/calculator`, `/trades`, `/world`, `/ecoregion`, `/climate`, and `/users`.

## Migration order

* **Wave 1, prove the path (complete)** - `list_public_servers`, `get_server_status`, currency, market, stores, logistics, civics, progression, and world now use typed shared registrations.
* **Wave 2, replace generic dispatch (complete)** - The remaining eleven straightforward read-only public tools now use typed shared registrations and explicit paths. `GET /preview/{tool}` remains a compatibility fallback for the two Wave 4 semantic exceptions.
* **Wave 3, add bounded model operations** - Introduce typed operations for food, price history, item activity, item search, recipes, professions, and specialties only after their stated bounds and disclosure prerequisites exist.
* **Wave 4, resolve semantic splits** - Add a transport-safe social input projection and split watcher reads from watcher mutations. Remove the dynamic preview adapter only after these exceptional tools have explicit safe behavior.

Each migration is complete only when the manual `Tool` entry and manual
Starlette route are removed, both transports call the same handler, input and
output schemas come from the typed models, transport errors remain public-safe,
and parity tests cover success, validation failure, and downstream failure.
