# Progression / skills history

Skill **trajectories** reconstructed from the Eco progression action-log
exporters. Where the jobs surface (`/api/v1/skills`, the `/jobs` page) shows
*current* skills - who holds which specialty at what level right now - this
surface shows **how** citizens got there: when each profession and specialty was
gained, level-up cadence, classes completed, and enrollments. Everything is
already exported, so there is no new C# mod and no game reset. Filed as
[#64](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/64), under the
pull-everything survey [#7](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/7).

## Surfaces

- **`get_eco_progression` MCP tool** - `src/eco_mcp_app/progression.py` + `server.py` wiring. Returns a markdown summary + the structured `ProgressionHistory.to_dict()` JSON, plus an `_meta.ui` Jinja card (`templates/partials/progression.html`) for MCP Apps hosts. Requires an admin API key server-side (`ECO_ADMIN_API_KEY`, SSM in the homelab deploy).
- **`/progression` SPA page** - `frontend/src/pages/Progression.tsx`, consuming `/preview/progression.json`. Product UX lives here (the Jinja card is only the in-chat fragment). Carries the per-day trend small-multiples, the leaderboards, and expandable per-citizen trajectory cards, with a `?q=` citizen filter and cross-links to `/jobs` (current state) and `/crafting` (skill provenance).
- **`/jobs` history lane** - `frontend/src/pages/Jobs.tsx` fetches the same surface best-effort and enriches each player card with a "how they got here" expandable timeline, joined to the progression citizen by name. A failure or thin server leaves `/jobs` exactly as it was - the lane simply doesn't render.

## Data source

Seven progression action exporters, each fetched from
`GET /api/v1/exporter/actions?actionName=<name>`:

    GainProfession, GainSpecialty, LoseSpecialty, SpecialtyLevelUp,
    CharacterLevelUp, CompleteClass, EnrollAction

Plus best-effort discovery of up to three progression **daily series** by
scanning `/datasets/flatlist` for progression-specific name keywords and folding
whatever `/datasets/get` returns (`SERIES_DISCOVERY_KEYWORDS`). The
action-derived trends stand alone, so a missing / mismatched catalog just yields
no series rather than blocking the surface.

## What the history computes

- **Per-citizen trajectories** - a chronological event timeline plus derived summaries: professions gained, currently-held specialties (a gain is "current" unless a later loss cancels it), highest character level, and level-up count. Busiest citizens first, capped at `ECO_PROGRESSION_MAX_CITIZENS` (default 80); each timeline capped at `ECO_PROGRESSION_TIMELINE_ROWS` (default 60) while the summaries see every event.
- **Server-wide trends** - per-in-game-day counts of each event kind (specialties gained, level-ups, professions, classes, enrollments), rendered as single-hue small-multiples on `/progression`.
- **Leaderboards** - most-gained specialties, most-gained professions, class completions, and busiest levelers.

## Messy bits handled

- **Numeric citizen ids** - `Citizen` is a numeric in-game id. Joined to names via the jobs mod's `/api/v1/citizens` surface (shared `crafting.fetch_citizen_name_map`), falling back to `Citizen #<id>` when a name is missing. The id→name link is [#5](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/5).
- **Column-shape uncertainty** - the progression exporters weren't reachable from the build container to capture a live header (public server down, no admin key), so the skill / profession / class / level column *names* are best-effort candidates (`SKILL_COLUMNS`, `LEVEL_COLUMNS`) drawn from Eco's `GameActions` field conventions. The parser keys off the header and picks the first matching candidate per semantic field, so an unexpected name degrades to a blank skill rather than a wrong row. The citizen id, time, and per-action counts anchor on universal columns and stay correct regardless. Mirrors the `BoughtOrSold` posture the trades ledger took ([#6](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/6)).
- **Time semantics** - integer seconds since cycle start, same convention as the species population CSV: in-game day = `Time / 86400` (`SECONDS_PER_DAY`).
- **Misalignment risk** - some exporter rows carry an undeclared extra column that shifts every later field. Reuses `crafting._corrected_index` so header-keyed picks stay aligned, and blanks position-triple / bare-number values where a name belongs ([#5](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/5)).

## Streaming & caching

Progression logs grow all cycle, so the aggregator stream-parses via
`crafting._stream_csv_rows` + a batched fold (never buffering the whole body),
capped at `ECO_PROGRESSION_MAX_ROWS` per action. Results are cached in an
in-process `TTLCache` keyed per (base URL, api-key hash), TTL
`ECO_PROGRESSION_CACHE_TTL` (default 60s), mirroring the trades ledger.

## Follow-ups

- Capture the live progression exporter headers when the server + admin key are reachable, and confirm the `SKILL_COLUMNS` / `LEVEL_COLUMNS` candidate names (and the three progression daily-series names) against Eco's `GameActions` source. Update the candidate lists / discovery keywords if they differ.
- Confirm whether the jobs-mod specialty ids match the progression exporter's `Specialty` column form (with or without a `Skill` suffix); the `/jobs` history lane joins citizen-by-name, but a specialty-name mismatch would only affect cosmetic prettifying, not the join.
