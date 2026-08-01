# Agent instructions

Workspace conventions load globally via `~/.claude/CLAUDE.md`. This file covers only what is specific to this repo.

## Scope

The Eco application monorepo: one fused Python service (MCP + SPA + jobs API), a local replay browser, and the in-game C# plugins that feed them. Consolidated per [coilysiren/inbox#101](https://forgejo.coilysiren.me/coilysiren/inbox/issues/101).

## Project shape

- `src/eco_mcp_app/` - the core service. `server.py` is the MCP server, `__main__.py` the stdio entry for Claude Desktop, `http_app.py` the Starlette ASGI app.
- `src/eco_spec_tracker/` - jobs JSON API (FastAPI), mounted at `/jobs/api`. The jobs UI is the SPA's `/jobs` route.
- `src/eco_replay/` - FastAPI browser for the replay mod's SQLite event log. Local-only.
- `frontend/` - Vite + React + TypeScript SPA, served at `/` by the fused service. Built in the Dockerfile's node stage; local dev via `ward exec frontend-dev` against `ward exec http`.
- `mods/jobs/`, `mods/replay/`, `mods/telemetry/` - C# Eco server plugins. jobs and replay share DTO contracts with their Python consumers, so they live here, not in eco-mods.
- `data/ecoregions.json` - bundled WWF ecoregion definitions. Species/ecopedia lookups go to live web fetches.
- `data/eco_gnome_data.json` - the vendored, en-US-trimmed vanilla Eco recipe graph. `data/eco_gnome_data.LICENSE.txt` carries its attribution.
- `tests/mcp/`, `tests/jobs/` - per-component pytest suites under one `tests/` root.
- `investigation/` - preserved post-mortem from eco-mcp-app. Read before questioning weird-looking decisions.
- `Dockerfile` - the single fused image, entrypoint `eco_mcp_app.http_app:app` on port 4000.

## Repo boundaries

This repo is the application layer (`infra -> eco-app -> deploy`). Its deploy surface (k8s manifests, rollout) lives in `coilyco-bridge/deploy/services/eco-app`, never here. Gameplay mods belong in `coilyco-gaming/eco-mods`.

## Commands

Route every dev command through the ward gate as `ward exec <verb>`. The canonical allowlist is [`.ward/ward.yaml`](.ward/ward.yaml). Each verb invokes one tool directly or delegates shell behavior to the focused [`scripts/ward-command.sh`](scripts/ward-command.sh) dispatcher.

## Validation

- `ward exec test` - pytest across tests/mcp and tests/jobs.
- `ward exec lint` - ruff check + format check + mypy.
- `ward exec smoke` - stdio MCP round-trip.
- `ward exec precommit` - the managed agentic-os hook suite. Opt-outs live under `[tool.agentic-os.*]` in `pyproject.toml`.

## Safety

Keep every artifact public-safe. Opaque ids, tokens, and sensitive hosts go in AWS SSM, never tracked files. Telemetry endpoints stay in the deploy repo, never hardcoded in application source.

## Cross-repo contracts

- `coilyco-bridge/deploy` - owns this service's manifests and rollout. A change to ports, env vars, or secrets here needs a matching change there.
- `coilyco-gaming/eco-mods` - gameplay mods and their Unity assets.
- Catalog metadata lives in the `catalog:` block of `.ward/ward.yaml`. Update [docs/FEATURES.md](docs/FEATURES.md) whenever a feature is added or reshaped.

## Release

Canonical history lives on Forgejo (`coilyco-gaming/eco-app`). CI tests,
builds, and publishes the private single-architecture image as
`forgejo.coilysiren.me/coilyco-gaming/eco-app:<full-source-sha>` on every push
to `main`. The trusted publisher verifies the remote manifest. A commit to
`main` is not a deploy. Rollout is driven from `coilyco-bridge/deploy` through
a separate read-only package credential.

## Agent rules

Name the actor in action sentences. Route every command through the gate, never bare tooling. Pull every server dataset that could be remotely interesting - code is cheap, the game server is colocated, CPU is fine. Interesting-but-messy data gets a Forgejo cleanup issue, never a silent skip.

**Product UX is the SPA (`frontend/`).** Server HTML is only the MCP `_meta.ui` card - never build browser UI as an iframe/Jinja card.

## See also

- [README.md](README.md) - human-facing intro.
- [docs/FEATURES.md](docs/FEATURES.md) - inventory of what ships today.
- [docs/datasets/README.md](docs/datasets/README.md) - dataset survey + probe how-to.
- [.ward/ward.yaml](.ward/ward.yaml) - allowlisted commands.

Cross-reference convention from [coilysiren/agentic-os#59](https://github.com/coilyco-flight-deck/agentic-os/issues/59).
