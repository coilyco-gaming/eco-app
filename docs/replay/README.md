# eco-replay

Player-action recorder for an [Eco](https://play.eco/) server, plus a small browser UI.

Built as a clean-room alternative to the closed-source `Chronicler` mod (mod.io), which ships Windows-only native SQLite and doesn't run on Linux servers. eco-replay is two pieces:

1. **C# Eco mod** (`mod/src/`) — implements `IGameActionAware`, receives every `GameAction` Eco produces, and appends a row to SQLite (`Storage/EcoReplay.db`). Uses `Microsoft.Data.Sqlite` which bundles a Linux-native `libe_sqlite3.so` via `SQLitePCLRaw`, so it Just Works on Linux without a Windows interop dance.
2. **FastAPI web app** (`src/eco_replay/`) — reads the mod's `GET /api/v1/events?citizen=&type=&limit=` JSON endpoint and renders a filterable HTMX/Tailwind UI.

Same pattern as the sibling [`eco-jobs-tracker`](../eco-jobs-tracker): mod is source of truth, web app is the view.

## Quick start

```sh
# Compile and stage the mod into the live EcoServer:
make install-mod
make restart-eco
make tail-eco          # watch logs for "Initializing EcoReplay..."

# Browse events:
make build-native
UPSTREAM_URL=http://localhost/api/v1/events make run-native
# http://localhost:4200/
```

Mock mode (no UPSTREAM_URL) returns canned events so the UI can be developed without an Eco server.

## What gets recorded

Every `GameAction` Eco fires through `ActionUtil.ActionPerformed`. The recorder pulls out:

- `action_type` — class name (`ChatSent`, `PlaceBlock`, `CraftItem`, …)
- `citizen` — the user performing the action (via reflection on the `Citizen` property)
- `unix_time` / `game_time` — when
- `body_json` — best-effort flat JSON of the action's other properties (User/ItemStack/WorldObject references collapse to their `Name`)

## Storage

`Storage/EcoReplay.db` next to Eco's own `Game.db`. WAL mode, indexed on `unix_time`, `action_type`, and `citizen`. Rides Eco's existing `Storage/Backup/*` backup loop for free.

## Endpoints

| Path | Description |
|---|---|
| `GET /api/v1/events` | List events. Query: `citizen`, `type`, `limit` (≤1000), `since` (unix seconds). |
| `GET /api/v1/events/stats` | `{ ready, total }` |

## See also

- [`mod/src/EcoReplay.csproj`](mod/src/EcoReplay.csproj) — mod targets net10.0, Eco.ReferenceAssemblies 0.13-beta.
- [`docs/`](docs/) — design notes.
