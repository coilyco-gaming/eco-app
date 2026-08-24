[![Eco by Strange Loop Games](https://cdn.cloudflare.steamstatic.com/steam/apps/382310/header.jpg)](https://store.steampowered.com/app/382310/Eco/)

<sub>Banner: Steam header for Eco by [Strange Loop Games](https://strangeloopgames.com/). Used here for attribution, not my artwork.</sub>

# eco-app

The companion service for the Sirens [Eco](https://play.eco/) server. It turns
live world, trade, crafting, civics, and player state into practical answers,
for an agent over MCP or a person in a browser.

## One fused service

`eco_mcp_app` is the core, a data-only MCP server reachable over stdio for
Claude Desktop and Streamable-HTTP at `/mcp/`, whose tools return markdown and
structured JSON. Tool names are task-shaped and do not repeat the product name,
so `get_server_status` and `get_region` rather than `get_eco_status`.

Mounted inside it: the jobs API at `/jobs/api`, shaping rows out of the in-game
skills mod, and `eco_replay`, a reader over the replay mod's append-only JSONL
event log. `frontend/` is the Vite, React, and TypeScript SPA the same service
serves at `/`, with `/jobs` and `/replay` pages over those two.

## The in-game half

`mods/` holds the C# Eco server plugins that feed it: `jobs` for the skills
API, `replay` for the player-action event store, `stores` for live store and
currency export, and `telemetry` for logs, metrics, and exception capture.

Gameplay mods live in the sibling
[eco-mods](https://forgejo.coilysiren.me/coilyco-gaming/eco-mods) repo, not
here. Main CI builds every real mod project and publishes install-ready ZIPs to
Forgejo Packages, per [docs/mod-packages.md](docs/mod-packages.md).

## The operator surface is separate and bounded

A feature-flagged privileged MCP at `/admin` is the inside-out operator view.
Its fourteen `admin_*` tools read fixed read-only Eco state mounts and
node-local status, plus twelve enum-only observational RCON queries. It has no
arbitrary path, no free-form command, and no write capability. The `admin_`
prefix is a deliberate security-boundary signal rather than namespacing. See
[docs/admin-mcp.md](docs/admin-mcp.md).

## Run it

```sh
just http           # the fused server against a live eco target
just http-offline   # the same, against the local snapshot fixture
just frontend-dev   # Vite with HMR on :5173, proxying the API
```

`just` alone lists every recipe. Each push to canonical `main` publishes the
fused image as
`forgejo.coilysiren.me/coilyco-gaming/eco-app:<full-source-sha>`, and deploy
consumes that exact reference through a separate read-only credential.

## See also

- [AGENTS.md](AGENTS.md) - agent-facing operating rules.
- [docs/FEATURES.md](docs/FEATURES.md) - inventory of what ships today.
- [docs/admin-mcp.md](docs/admin-mcp.md) - the privileged surface and its disclosure contract.
- [justfile](justfile) - dev verbs.
- [.ward/ward.yaml](.ward/ward.yaml) - catalog metadata only.
