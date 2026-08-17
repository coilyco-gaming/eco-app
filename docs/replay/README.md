# eco-replay ("Kaihronicler")

Player-action recorder for an [Eco](https://play.eco/) server, surfaced read-only on the website.

eco-replay is a clean-room alternative to the closed-source `Chronicler` mod. It has two pieces:

1. **C# Eco mod** (`mods/replay/src/`) - implements `IGameActionAware`, receives each `GameAction` Eco produces, and appends one JSON object per line to `Storage/EcoReplay.jsonl`. It has no SQLite package or native runtime dependency.
2. **FastAPI JSON API** (`src/eco_replay/`) - reads the mod's `GET /api/v1/events?citizen=&type=&limit=` HTTP endpoint, the JSONL file directly through `ECO_REPLAY_FILE`, or a mock fallback. It re-serves events as `/v1/events`, `/v1/events/stats`, and `/v1/meta`. The fused service mounts it at `/replay/api`, and the SPA renders it at `/replay`.

The mod is the source of truth, the Python API is a thin re-server, and the SPA is the view.

## Quick start

The replay API rides the fused service, with no separate process:

```sh
just build-mod-replay
just http
just frontend-dev
```

Open `/replay` in the frontend. Set `ECO_REPLAY_FILE` to the recorder's JSONL path or set `ECO_REPLAY_UPSTREAM_URL` to the mod's `/api/v1/events` endpoint. With neither value set, the API returns canned mock events and the SPA shows a mock-data banner.

`ECO_REPLAY_UPSTREAM_URL` is deliberately separate from the jobs `UPSTREAM_URL`, so the fused process can read both mod endpoints. If a configured source rejects, times out, cannot be read, or returns malformed JSON, `/replay/api/v1/events` and `/stats` return a public-safe `503` response with `error.code: replay_upstream_unavailable`. The SPA clears the timeline and shows its unavailable state.

## What gets recorded

Every `GameAction` Eco fires through `ActionUtil.ActionPerformed`. Each JSONL row carries:

* `id` - monotonic event id, recovered from persisted rows after restart.
* `unixTime` and `gameTime` - the wall and game clocks.
* `type` - action class name.
* `citizen` - the acting user when available.
* `body` - best-effort bounded JSON for the action's remaining properties.

`ItemCraftedAction` is intentionally the exception to the generic body snapshot. Each `WorkOrder.CompleteIteration` becomes one row with a fixed scalar `craft-iteration/v1` body containing item, station, byproduct, position, and `iterations: 1`. This keeps each completed craft attributable without serializing a live Eco object graph.

## Storage and retention

`Storage/EcoReplay.jsonl` is an append-only, UTF-8 newline-delimited JSON file next to Eco's other storage. The background writer owns a bounded 4,096-row channel and writes in batches, so event recording never performs disk I/O on the game thread. A saturated queue sheds new rows instead of blocking the server.

The store retains the newest 2,000,000 valid rows. Compaction streams the existing file into a temporary sibling and atomically replaces only the JSONL file on the same filesystem. Queries also stream the file and retain only their bounded newest-result window in memory. Malformed rows and a partial final line are skipped.

The legacy `Storage/EcoReplay.db` is not deleted, rewritten, read, or silently imported. It remains a recoverable historical archive. Importing old rows is a separate operator-approved task because deduplication and backup boundaries need live evidence.

## Endpoints

The C# mod serves:

* `GET /api/v1/events` - list events. Filters are `citizen`, `type`, `limit` up to 1,000, `since` in Unix seconds, and exclusive `beforeId` pagination.
* `GET /api/v1/events/stats` - return `{ ready, total }` for valid persisted rows.

The Python API re-serves:

* `GET /replay/api/v1/events` - list events with `citizen`, `type`, and `limit` filters.
* `GET /replay/api/v1/events/stats` - return `{ ready, total }`.
* `GET /replay/api/v1/meta` - return `{ mockData }` so the SPA can label its fixture state.

## Validation

* `just test` covers direct-file filtering, limits, counts, malformed rows, and partial final lines.
* `just build-mod-replay` verifies the mod compiles without SQLite packages or native assets.
* `just test-mod-replay` covers append, filters, limits, retention, restart id recovery, malformed rows, partial rows, and bounded-queue behavior.

## See also

* [`mods/replay/src/EcoReplay.csproj`](../../mods/replay/src/EcoReplay.csproj) - the net10.0 Eco mod project.
* [docs/FEATURES.md](../FEATURES.md) - the shipped capability inventory.
