# Snapshot dev harness

Take a point-in-time snapshot of every data source the app consumes, park it in S3, and replay it locally so the whole fused service iterates offline. Landed via [#128](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/128).

## Why

The app's only upstream is the live Eco game server (plus its in-game mods). Iterating against it couples the dev loop to server reachability, mutates nothing but observes a moving world, and makes bug repro non-deterministic day to day. A snapshot freezes one world state, S3 makes it shareable across machines, and the fixture server makes it the app's upstream with a single env var.

## The loop

* `ward exec snapshot-capture` - resolves the eco target (same path as `http`), pulls every endpoint into `.snapshots/current/`, byte-for-byte, indexed by `manifest.json`. Failures are recorded in the manifest, never silently skipped.
* `ward exec snapshot-push` - tars the dir and uploads `s3://kai-game-backups/eco-app/snapshots/<utc-stamp>.tar.gz`, then server-side copies it over `latest.tar.gz`.
* `ward exec snapshot-pull` - downloads `latest` and extracts into `.snapshots/current/`. Pass `-- --snapshot <stamp>` to select another capture.
* `ward exec snapshot-serve` - replays the snapshot as a fixture eco server on `localhost:3101`.
* `ward exec http-offline` - runs the fused server with `ECO_INFO_URL` pointed at the fixture and a dummy admin token, so every surface (MCP tools, `/preview/*.json`, `/jobs`, SPA data plane) serves from the snapshot.

Two terminals total: `snapshot-serve` in one, `http-offline` in the other. `.snapshots/` is gitignored, snapshots live in S3 only.

## What gets captured

`src/eco_snapshot/capture.py` holds the endpoint list, which is the union of everything in the [dataset survey](datasets/README.md):

* Catalog-driven fan-out - `/datasets/flatlist` drives one request per series (`/datasets/get`, day window from `/info` `DaysRunning`) and one per action exporter CSV (`/api/v1/exporter/actions`). `/api/v1/exporter/specieslist` drives the per-species CSVs. A dataset added next cycle is captured with no code change.
* Static surfaces - `/info`, users, laws, elections + titles, currency holdings, worldlayers, map dimension + property, climate settings, and every catalog-advertised `/Layers/<LayerName>.gif` raster (including the world preview and optional pollution layer). A disabled raster remains a manifest failure.
* Mod surfaces - jobs (`/api/v1/skills`, `/api/v1/citizens`), stores (`/api/v1/stores`), replay (`/api/v1/events`, `/api/v1/events/stats`). Replay capture follows the mod's exclusive `beforeId` cursor in 1,000-row pages until the complete event history is exhausted.

Out of scope: the external species-enrichment fetches (Wikipedia, iNaturalist, Wikidata, FRED). Those are not eco-server data, and the app already degrades gracefully without them.

## Replay matching

`src/eco_snapshot/serve.py` looks an incoming GET up in the manifest in this order:

1. Exact path + canonicalized query.
2. Significant-param match - `manifest.SIGNIFICANT_PARAMS` names the params that identify a resource per path (`dataset`, `actionName`, `speciesName`), so a request whose volatile day window differs from capture time still hits the right series.
3. Path-only, when the snapshot holds exactly one entry for that path.
4. A loud 404 naming the miss, so a gap in the capture list surfaces in the dev loop instead of reading as empty data.

Auth is ignored on purpose. The snapshot already dropped everything the admin key gated, and the fixture binds to localhost. `GET /_snapshot` returns capture metadata (when, from where, entry count, failures).

## Conventions

* The admin key rides `UPSTREAM_API_KEY` from SSM `/eco-mcp-app/api-admin-token`, fetched inside the `snapshot-capture` Ward verb. It never lands in the snapshot or argv.
* Snapshots are prod-shaped public-safe game data plus player names, same exposure class as the live public endpoints they mirror. The bucket stays private regardless.
* S3 verbs live in `scripts/ward-command.sh` and route AWS access through `ward-kdl ops aws`.

## See also

* [infrastructure docs/eco-staging.md](https://forgejo.coilysiren.me/coilyco-flight-deck/infrastructure/src/branch/main/docs/eco-staging.md) - the sibling harness one layer down: snapshots the eco **server itself** (code + world save) to S3 and restores it as a neutered staging server on kai-server. This doc's harness snapshots the server's **data API surface** for the app's offline dev loop; the staging harness clones the server for mod/config iteration (e.g. eco-app#134).
