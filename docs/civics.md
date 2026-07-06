# Civics & governance

The **history + trend** half of the governance surface, reconstructed from data
the Eco server already exports - no game restart, no new C# mod. Where
`get_eco_government` (the `/server` law/title card) is the *current-state*
snapshot - who holds which title, which laws are active right now - this surface
is the record of civic *events* over time: who ran, who voted, who moved in, and
where new settlements rose. Filed as
[#61](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/61), the
largest unconsumed vein in the pull-everything survey
([#7](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/7)) and the
biggest remaining DiscordLink-parity gap under the epic
([#37](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/37)).

## Surfaces

- **`get_eco_civics` MCP tool** - `src/eco_mcp_app/civics.py` + `server.py` wiring. Returns a markdown summary + the structured `CivicsReport.to_dict()` JSON. Civics is a "just data" tool - it emits no MCP-app widget ([#87](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/87); the widget is scoped to the world/region view). Requires an admin API key server-side (`ECO_ADMIN_API_KEY`, SSM in the homelab deploy).
- **`/preview/civics.json` data plane** - `http_app.py` dispatches the tool and returns its JSON block, the short stable path the SPA consumes.
- **`/civics` SPA page** - `frontend/src/pages/Civics.tsx`. Product UX lives here (the Jinja card is only the in-chat fragment): a civic stat grid, a two-series turnout-over-time chart, recent elections, a most-active-voter leaderboard, new settlements, and recent arrivals/departures. Cross-links `/economy` and `/server`, with a live homepage badge (`useCivicsPulse`).

## Data sources

Two planes, both already live on the server:

- **Action rows** - `GET /api/v1/exporter/actions?actionName=<Name>`, one CSV row per civic event. Consumed:
  - Elections - `StartElection`, `Vote`, `DidntVote`, `JoinOrLeaveElection`, `WonElection`, `LostElection`
  - Demographics - `BecomeCitizen`, `LeaveCitizenship`, `ResidencyChanged`, `DemographicChange`
  - Settlements - `SettlementFounded`, `PlaceNewSettlementFoundation`, `StartHomestead`
- **Daily series** - `GET /datasets/get?dataset=<Name>` for the civic counters (`CIVICS_SERIES`). The same names double as datasets on the server (an action dataset also exposes a daily count series - the `ECONOMY_DATASETS` pattern), giving turnout / demographic / settlement counts **over time** for the trend charts. Fetched best-effort; an unknown or empty series is skipped, never fatal.

## What the report computes

- **Elections & turnout** - elections started + outcomes (won/lost), votes cast vs abstentions with a participation rate, and a most-active-voter leaderboard. The turnout-over-time chart draws the `Vote` and `DidntVote` daily series as two lines on one shared axis (same unit - a daily count).
- **Demographics** - citizens gained (`BecomeCitizen`) minus lost (`LeaveCitizenship`) for a net, residency moves (`ResidencyChanged`), and a recent arrivals/departures table.
- **Settlements** - settlements founded (`SettlementFounded` / `PlaceNewSettlementFoundation`) and homesteads started (`StartHomestead`), each with the founding citizen.
- **Trend** - the per-series daily counts, keyed by series name, converted to an in-game-day x-axis.

## Messy bits handled (the pull-everything cleanups)

- **Numeric actor ids** - the acting `Citizen` (voter / proposer / winner / founder) is a numeric in-game id, joined to a display name via the jobs mod's `/api/v1/citizens` surface (shared `crafting.fetch_citizen_name_map`), falling back to `Citizen #<id>` when a name is missing ([#5](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/5)).
- **Unknown civic headers** - the exact civic CSV column layouts weren't captured live this cycle ([#7](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/7) is inventory-only for the civics families). The parser keys off the header and scans a generous per-action candidate list (`_SUBJECT_CANDIDATES`, `_CITIZEN_CANDIDATES`) for the subject + actor; a miss just leaves that field blank, so the per-type counts and turnout still carry the report. When the live headers are probed, tighten the candidate lists.
- **Time semantics** - integer seconds since cycle start, same convention as the species population CSV and the trades ledger: in-game day = `Time / 86400` (`SECONDS_PER_DAY`).
- **Misalignment risk** - some exporter rows carry an undeclared extra tool column that shifts every later field. The report reuses `crafting._corrected_index` (scores candidate insertion points against per-column value shapes) so header-keyed picks stay aligned ([#5](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/5)).
- **Laws-in-effect** - not derivable from the action stream (there is no per-law event). The surface points at `get_eco_government` / `/server` for the active-law list rather than fabricating one.

## Streaming & caching

Civic logs grow late-cycle, so the report stream-parses via
`crafting._stream_csv_rows` + a batched fold (never buffering the whole body),
capped at `ECO_CIVICS_MAX_ROWS` per action. Results are cached in an in-process
`TTLCache` keyed per (base URL, api-key hash), TTL `ECO_CIVICS_CACHE_TTL`
(default 60s), mirroring `trades._trades_cache`.

## Follow-ups

- Probe the live civic CSV headers and the exact civics/people series names against `/datasets/flatlist` (the [#7](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/7) survey left both families inventory-only), then tighten `_SUBJECT_CANDIDATES` / `CIVICS_SERIES` to the real columns and drop the best-effort scan.
- Link each `WonElection` / `LostElection` outcome back to its `StartElection` by election id once the subject column is confirmed, for per-election turnout rather than the current global turnout.
