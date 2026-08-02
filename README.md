[![Eco by Strange Loop Games](https://cdn.cloudflare.steamstatic.com/steam/apps/382310/header.jpg)](https://store.steampowered.com/app/382310/Eco/)

<sub>Banner: Steam header for Eco by [Strange Loop Games](https://strangeloopgames.com/). Used here for attribution; not my artwork.</sub>

# eco-app

The application monorepo for the "Eco via Sirens" game server's companion services, consolidating four former repos (eco-mcp-app, eco-jobs-tracker, eco-replay, eco-telemetry) into one deployable. See [coilysiren/inbox#101](https://forgejo.coilysiren.me/coilysiren/inbox/issues/101) for the merge rationale.

One fused service ships from this repo. `eco_mcp_app` is the core: a data-only MCP server (Claude Desktop over stdio, hosts over Streamable-HTTP at `/mcp/`) whose tools return markdown and structured JSON. The jobs JSON API (`eco_spec_tracker`, row-shaping over the in-game skills mod) mounts inside it at `/jobs/api`, and the jobs UI is the SPA's `/jobs` page. `eco_replay` is the mounted FastAPI reader for the replay mod's append-only JSONL event log, consumed by the SPA's `/replay` page.

MCP tool names are scoped to their owning server and do not repeat the Eco
product name. Public tools use task names such as `get_server_status` and
`get_region`. The privileged server retains an `admin_` prefix as an explicit
security-boundary signal.

Every push to canonical `main` publishes the private fused image as
`forgejo.coilysiren.me/coilyco-gaming/eco-app:<full-source-sha>`. The trusted
publisher verifies the remote manifest. Deploy consumes that exact reference
through a separate read-only package credential.

`frontend/` is the browser face: a Vite + React + TypeScript SPA the fused service serves at `/`, headed for `eco-app.coilysiren.me`. It is the intelligence and companion layer for serious Eco servers, turning live world, trade, crafting, civics, and player data into practical answers.

The feature-flagged privileged MCP at `/admin` is the inside-out operator
surface. Its fourteen `admin_*` tools read fixed read-only Eco state mounts
and node-local status, then add twelve enum-only observational RCON queries. It
has no arbitrary path, free-form command, or write capability. See
[docs/admin-mcp.md](docs/admin-mcp.md) for its capability and disclosure
contract.

The in-game halves live under `mods/` as C# Eco server plugins: `mods/jobs` (skills API the tracker consumes), `mods/replay` (player-action event store), `mods/stores` (live store and currency export), and `mods/telemetry` (logs, metrics, and exception capture). The Docker build compiles and packages every real mod project, and main CI publishes the install-ready ZIPs to Forgejo Packages using the contract in [docs/mod-packages.md](docs/mod-packages.md). Gameplay mods live in the sibling [eco-mods](https://forgejo.coilysiren.me/coilyco-gaming/eco-mods) repo, not here.

## Commands

Dev commands are declared in [`.ward/ward.yaml`](.ward/ward.yaml). Run them as `ward exec <verb>`.

## See also

- [AGENTS.md](AGENTS.md) - agent-facing operating rules.
- [docs/FEATURES.md](docs/FEATURES.md) - inventory of what ships today.
- [docs/discord-bot.md](docs/discord-bot.md) - implementation specification for rich Discord slash-command embeds.
- [.ward/ward.yaml](.ward/ward.yaml) - allowlisted commands. Agents route through ward, not bare `make` / `uv` / `python` / `dotnet`.

Cross-reference convention from [coilysiren/agentic-os#59](https://github.com/coilyco-flight-deck/agentic-os/issues/59).
