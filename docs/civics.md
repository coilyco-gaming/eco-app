# Civics and governance

The history-and-trend half of the governance surface, reconstructed from data
the Eco server already exports: no game restart, no new C# mod. Where
`get_government` is the current-state snapshot, this is the record of civic
events over time. Filed as #61, the largest unconsumed vein in the
pull-everything survey (#7) and the biggest DiscordLink-parity gap (#37).

## Surfaces

- **`get_civics`** - `src/eco_mcp_app/civics.py` plus `server.py` wiring.
  Returns markdown plus `CivicsReport.to_dict()`. Requires `ECO_ADMIN_API_KEY`
  server-side, from SSM in the homelab deploy.
- **`/preview/civics.json`** - the short stable path the SPA consumes.
- **`/civics`** - `frontend/src/pages/Civics.tsx`: a civic stat grid, a
  two-series turnout chart, recent elections, a most-active-voter leaderboard,
  new settlements, and recent arrivals and departures.

**Data sources.** Two planes, both already live. **Action rows** from
`GET /api/v1/exporter/actions?actionName=<Name>`, one CSV row per civic event,
covering elections (`StartElection`, `Vote`, `DidntVote`,
`JoinOrLeaveElection`, `WonElection`, `LostElection`), demographics
(`BecomeCitizen`, `LeaveCitizenship`, `ResidencyChanged`, `DemographicChange`),
and settlements (`SettlementFounded`, `PlaceNewSettlementFoundation`,
`StartHomestead`). Plus the civics and people **series** from the dataset
flatlist.

**What it computes.** Elections started and their outcomes, votes cast against abstentions with a
participation rate, and a most-active-voter leaderboard. The turnout chart
draws `Vote` and `DidntVote` as two daily-count lines on one shared axis.

The acting `Citizen` is a numeric in-game id, joined to a display name through
the jobs mod's `/api/v1/citizens` (shared `crafting.fetch_citizen_name_map`),
falling back to `Citizen #<id>` when a name is missing (#5).

Civic logs grow late-cycle, so the report stream-parses through
`crafting._stream_csv_rows` and a batched fold, never buffering the whole body,
capped at `ECO_CIVICS_MAX_ROWS` per action. Results cache in an in-process
`TTLCache` keyed per base URL and api-key hash, TTL `ECO_CIVICS_CACHE_TTL`
(default 60s), mirroring `trades._trades_cache`.
