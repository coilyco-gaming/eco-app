# World, climate, and biodiversity

The SPA's `/map` route is the readable state-of-the-world surface. It keeps the live map, biome and water composition, climate evidence, nearest real-world ecoregion matches, biodiversity movement, and species risk. The literal **Mutation timeline** section and everything below it were removed in [#191](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/191). Activity hotspot circles were removed from the map in [#190](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/190).

## Map and environmental state

The World page consumes three independent planes:

* `/preview-map.json` - the map image and owner-coloured property deed polygons. Owner names can contain Eco rich-text markup, which the SPA parses through a safe allow-list renderer rather than raw HTML.
* `/preview/get_region.json` - biome and water composition, nearest ecoregion matches, biodiversity drift, and per-species risk evidence.
* `/preview/get_climate.json` - CO2, temperature, sea level, source and sink breakdowns, freshness, and read-only coordination guidance.

Each plane degrades independently. The page does not fetch or render the world-mutation action summary. The backend `get_world` MCP tool and `/preview/world.json` data plane remain available for structured action analysis and existing consumers.

## Climate source freshness

The climate backend preserves each dataset response's source `Unit` and `Interval` metadata alongside its points. Every headline KPI exposes its latest source game-time sample, current game day, source cadence, cadence lag, and a `current`, `stale`, or `unknown` freshness state. Freshness compares the dataset-series clock with the current game day. The backend fetch timestamp remains only a cache-observation timestamp and is never presented as the source observation.

The World page renders `TotalGroundPollution` as PPM, matching the dataset contract. A percentage is shown only when the series is unavailable and the page falls back to the world-layer summary. A daily series sampled on the current game day is current. A sample at least one source cadence behind is visibly stale. Legacy datasets that omit `Interval` retain their latest sample but report unknown cadence and unknown freshness rather than guessing. The backend's 60-second cache window and the browser page-load time remain separately labeled ([#184](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/184)).

## Biome and ecoregion evidence

`src/eco_mcp_app/ecoregion.py` reads the public world-layers endpoint and normalizes the biome vector before comparing it with the committed WWF-inspired ecoregion fixture. Salt water and fresh water are reclassified from the formerly undifferentiated biome gap, leaving the remainder as genuine mountain or transitional terrain. The SPA shows the three closest ecoregion matches and highlights biome rasters on map hover.

Species exporters provide one population series per species. The existing boom and bust summaries remain descriptive movement signals. They do not assert that a population is healthy.

## At-risk species

The World page adds a read-only species evidence board backed by deterministic relative rules. Eco does not expose a universal healthy population baseline, so the classifier compares each species only with its own observed series.

An **at risk** warning requires enough evidence and either condition:

* Current population is at or below 25% of that species' own observed peak, with a material absolute drop.
* Cycle decline is at least 30% and the recent window is still down at least 15%, again with a material absolute drop.

Classification requires at least four samples across 30 minutes. A series more than 30 minutes behind the newest exporter series is stale. Missing, stale, and insufficient series never produce a healthy or at-risk claim. Current evidence can also read declining, recovering, stable, or naturally sparse. Naturally sparse means the observed peak stayed at or below 25 without a relative collapse. It is not a global target.

Each row shows current population, absolute and relative cycle change, recent relative change, observation window, sample count, freshness, status, reason, and the threshold description. Every species links to `/species?name=<species>`, which renders the existing species profile and population curve. The surface is evidence for player coordination. It does not control hunting, harvesting, laws, or server configuration.

## World activity backend

`src/eco_mcp_app/world.py` still folds nine action exporters into construction, objects, roads, garbage, explosions, pollution, and extraction categories. It preserves streamed CSV parsing, defensive column realignment, citizen id-to-name joins, per-day buckets, category totals, world shapers, polluters, touched objects, and coarse activity hotspots for MCP and JSON consumers. This structured backend is intentionally separate from the reduced visual World page.

## Caching

World-layer data caches for five minutes, climate snapshots cache for one minute, and species series cache for one minute. The world-activity aggregate uses its own five-minute SQLite cache under `~/.cache/eco-mcp-app/world.sqlite`, keyed by server and API-key hash so servers do not cross-contaminate.

## See also

* [docs/FEATURES.md](FEATURES.md) - shipped capability inventory.
* [docs/datasets/README.md](datasets/README.md) - dataset survey and probe recipe.
* [docs/crafting](mcp/FEATURES.md) and [docs/trades.md](trades.md) - sibling action-log surfaces.
