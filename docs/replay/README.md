# eco-replay ("Kaihronicler")

Player-action recorder for an [Eco](https://play.eco/) server, surfaced read-only on the website.

Built as a clean-room alternative to the closed-source `Chronicler` mod (mod.io), which ships Windows-only native SQLite and doesn't run on Linux servers. eco-replay is two pieces:

1. **C# Eco mod** (`mods/replay/src/`) — implements `IGameActionAware`, receives every `GameAction` Eco produces, and appends a row to SQLite (`Storage/EcoReplay.db`). Uses `Microsoft.Data.Sqlite` which bundles a Linux-native `libe_sqlite3.so` via `SQLitePCLRaw`, so it Just Works on Linux without a Windows interop dance.
2. **FastAPI JSON API** (`src/eco_replay/`) — reads the mod's `GET /api/v1/events?citizen=&type=&limit=` HTTP endpoint (or the SQLite file directly via `ECO_REPLAY_DB`, or a mock fallback) and re-serves it as `/v1/events`, `/v1/events/stats`, and `/v1/meta`. Mounted at `/replay/api` inside the fused service; the browser UI is the SPA's `/replay` route (`frontend/src/pages/Replay.tsx`). The old Jinja/HTMX HTML surface was removed in [#38](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/38) — product UX is the SPA, per the repo's SPA-only rule (DLT epic [#37](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/37)).

Same pattern as the sibling [`eco_spec_tracker`](../../src/eco_spec_tracker): mod is source of truth, the JSON API is a thin re-server, the SPA is the view.

## Quick start

The replay API rides the fused service — no separate process. Point it at a data
source via env vars and run the SPA + service:

```sh
# Build the replay mod DLL (staged into the live EcoServer separately):
ward exec build-mod-replay

# Serve the whole site (SPA + all APIs, replay included) and browse /replay:
ward exec http                 # the fused service on :4000
ward exec frontend-dev         # Vite dev server against it, open /replay
```

Set `ECO_REPLAY_DB` (SQLite path) or `ECO_REPLAY_UPSTREAM_URL` (the mod's `/api/v1/events`
endpoint) on the service to pull the real Chronicle. With neither set the API
returns canned mock events so the `/replay` page can be developed without an Eco
server (the SPA shows a mock-data banner). `ECO_REPLAY_UPSTREAM_URL` is
deliberately separate from jobs' `UPSTREAM_URL`, so the fused process can read
both mod endpoints at once. If the configured replay upstream rejects, times
out, or returns malformed JSON, `/replay/api/v1/events` and `/stats` return a
public-safe `503` response with `error.code: replay_upstream_unavailable`; the
SPA clears the timeline and shows its unavailable state.

## What gets recorded

Every `GameAction` Eco fires through `ActionUtil.ActionPerformed`. The recorder pulls out:

- `action_type` — class name (`ChatSent`, `PlaceBlock`, `CraftItem`, …)
- `citizen` — the user performing the action (via reflection on the `Citizen` property)
- `unix_time` / `game_time` — when
- `body_json` — best-effort flat JSON of the action's other properties (User/ItemStack/WorldObject references collapse to their `Name`)

`ItemCraftedAction` is intentionally the exception to the generic body snapshot:
each `WorkOrder.CompleteIteration` becomes one row with a fixed scalar
`craft-iteration/v1` body (`item`, `station`, `byproduct`, `position`,
`iterations: 1`). Its citizen and clocks remain in the row columns. This keeps
every completed craft iteration attributable after the stats exporter rolls up,
without serializing any live Eco object graph.

## Storage

`Storage/EcoReplay.db` next to Eco's own `Game.db`. WAL mode, indexed on `unix_time`, `action_type`, and `citizen`. Rides Eco's existing `Storage/Backup/*` backup loop for free. The background writer has a 4,096-row bounded queue; a saturated disk sheds new rows instead of blocking the game thread. The database retains the newest 2,000,000 rows (about 38 days at the cited cycle-14 craft rate), pruning in batches so pages are reused rather than allowing unbounded growth.

## Endpoints

The C# mod serves these (consumed by the Python API as `ECO_REPLAY_UPSTREAM_URL`):

| Path | Description |
|---|---|
| `GET /api/v1/events` | List events. Query: `citizen`, `type`, `limit` (≤1000), `since` (unix seconds). |
| `GET /api/v1/events/stats` | `{ ready, total }` |

The Python API re-serves them under the fused service's `/replay/api` mount (consumed by the SPA's `/replay` route):

| Path | Description |
|---|---|
| `GET /replay/api/v1/events` | List events. Query: `citizen`, `type`, `limit` (≤1000). |
| `GET /replay/api/v1/events/stats` | `{ ready, total }` |
| `GET /replay/api/v1/meta` | `{ mockData }` — whether the events above are the canned mock set. |

## See also

- [`mods/replay/src/EcoReplay.csproj`](../../mods/replay/src/EcoReplay.csproj) — mod targets net10.0, Eco.ReferenceAssemblies 0.13-beta.
