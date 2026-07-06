# World & industry activity

The **physical** story of an Eco settlement: what players build, tear down,
terraform, move, blow up, throw away, and pollute. Where the crafting atlas
([docs/crafting](mcp/FEATURES.md)) reads the action log as *production* (what got
made) and the trades ledger reads it as *commerce* (what got sold), this surface
reads it as *world mutation* (what happened to the ground and the air). It is the
single largest unconsumed slice of the pull-everything survey
([#7](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/7)) - 20
exporters, no reset - filed as
[#62](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/62).

## No-reset spine

Every input is a world/industry **action exporter already live** on the server,
so there is **no new C# mod and no game restart**. The engine
(`src/eco_mcp_app/world.py`) reuses the crafting atlas's streamed-CSV plumbing
wholesale:

- `crafting._stream_csv_rows` - bounded, line-by-line CSV streaming (stays under
  the memory cap even on late-cycle multi-MB logs).
- `crafting._corrected_index` - the [#5](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/5)
  undeclared-extra-column corrector, so header-keyed picks stay aligned when the
  exporter inserts a stray tool column.
- `crafting.fetch_citizen_name_map` - the numeric-id → display-name join off the
  jobs mod's `/api/v1/citizens` surface (`Citizen #<id>` fallback).
- `trades.SECONDS_PER_DAY` - `Time` (seconds) → in-game day, matching every other
  time-bucketed surface.

## Exporters and categories

Nine action types fold into seven world-mutation **categories**:

| Action (`actionName=`)   | Category      |
|--------------------------|---------------|
| `ConstructOrDeconstruct` | construction  |
| `PlaceOrPickUpObject`    | objects       |
| `MoveWorldObject`        | objects       |
| `TampRoad`               | roads         |
| `DropOrPickupGarbage`    | garbage       |
| `ObjectExplosion`        | explosions    |
| `PolluteAir`             | pollution     |
| `DigOrMine`              | extraction    |
| `ChopTree`               | extraction    |

The extraction pair (`DigOrMine`, `ChopTree`) is re-framed **world-first** here -
the crafting atlas reads the same rows as production (the block/log you get), this
surface reads them as terraforming (the hole/stump you leave). Same rows, two
lenses. An action an admin has disabled 401/404s and becomes a non-fatal warning
rather than sinking the report - partial data is still the story.

## What the engine computes

Each CSV row is one **event**. `Count` (blocks placed, garbage dropped, ppm
emitted) accumulates as the category's **volume** and defaults to 1 when absent,
so a Count-less action still contributes.

- **Mutation timeline** - `day → {category: events}`, the raw material for the
  SPA's per-day stacked-by-category chart.
- **By category** - event count + summed volume per category.
- **Top world-shapers** - events per citizen across every category (id→name
  joined).
- **Top polluters** - events per citizen for the pollution category only, split
  out as the headline for the folded-in climate/atmosphere overlay (who is filling the air).
- **Most-touched objects** - the block / world-object / species id per event,
  weighted by volume and prettified.
- **Activity hotspots** - `ActionLocation` / `Position` floored to a 64-block x/z
  grid (the y/height axis dropped) and ranked by event count - "where the
  bulldozers are".

Positions and bare numbers that leak into a name slot (a residual misalignment
artifact) are dropped rather than rendered, mirroring the crafting atlas.

## Surfaces

- **`get_eco_world` MCP tool** - `world.py` + `server.py` wiring. Returns a
  markdown summary + the structured `WorldActivity.to_dict()` JSON, plus an
  `_meta.ui` Jinja card (`templates/partials/world.html`) for MCP Apps hosts.
  Requires an admin API key server-side (`ECO_ADMIN_API_KEY`, SSM in the homelab
  deploy).
- **`/preview/world.json` data plane** - a dedicated short path (passing
  `?server=` straight through) so the SPA hits a stable URL.
- **`/world` SPA page** - `frontend/src/pages/World.tsx`, consuming
  `/preview/world.json`. Product UX lives here (the Jinja card is only the in-chat
  fragment). The stacked timeline is a static inline SVG (no chart lib, CSP
  trivial) with a legend, a 2px surface gap between segments, and per-segment
  hover labels - the secondary encoding the categorical palette's CVD floor needs
  (hues are the dataviz skill's validated dark-mode theme, assigned by category
  identity, never by rank). The page is titled **World** and now carries the
  climate/atmosphere content inline as an environmental overlay ([#90](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/90))
  rather than cross-linking a separate `/climate` page; it cross-links `/crafting`
  and `/jobs`, and carries a live homepage badge, per the wave-0 SPA pattern.

## Caching

A tiny SQLite under `~/.cache/eco-mcp-app/world.sqlite` holds the last successful
aggregation + a fetched-at timestamp, TTL 5 min, keyed per `(base_url,
api_key_hash)` so swapping servers never cross-contaminates. Mirrors the crafting
atlas cache exactly.

## Probe how-to

    # one action's CSV (admin key required)
    curl -s -H "X-API-Key: $ECO_ADMIN_API_KEY" \
      "http://eco.coilysiren.me:3001/api/v1/exporter/actions?actionName=ConstructOrDeconstruct" | head

    # the folded surface, via the fused service
    curl -s http://localhost:4000/preview/world.json | jq '.categories, .hotspots[:3]'

Tuning knobs (env, all optional): `ECO_WORLD_CACHE_TTL`, `ECO_WORLD_MAX_ROWS`,
`ECO_WORLD_HOTSPOT_BIN`.

## See also

- [docs/FEATURES.md](FEATURES.md) - inventory of what ships today.
- [docs/datasets/README.md](datasets/README.md) - dataset survey + probe recipe.
- [docs/crafting](mcp/FEATURES.md) / [docs/trades.md](trades.md) - the sibling
  action-log surfaces this one shares plumbing with.
