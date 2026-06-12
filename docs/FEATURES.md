# eco-app features

Living inventory of what ships from this monorepo. Component-level detail lives in the per-component docs linked below, which were carried over from the four source repos during the consolidation ([coilysiren/inbox#101](https://forgejo.coilysiren.me/coilysiren/inbox/issues/101)).

## The fused service

One image, one uvicorn process, entrypoint `eco_mcp_app.http_app:app` on port 4000.

- **MCP server** - `src/eco_mcp_app/`, the core. Stdio for Claude Desktop, Streamable-HTTP at `/mcp/` for URL-connected hosts, browser preview surface at `/preview/*`. Full tool/resource inventory: [docs/mcp/FEATURES.md](mcp/FEATURES.md).
- **React frontend** - `frontend/`, a Vite + React + TypeScript SPA (no SSR). The Docker image builds it in a node stage and the fused service serves it at `/` (assets under `/assets`); a checkout without a build keeps the old `/` -> `/preview` redirect. The site is one flat surface ([#2](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/2)): the homepage is a thin directory of subpages (Server, Jobs, Server card, Community) with small live badges, and `/server` carries the live world snapshot from `/preview.json` (meteor countdown, players, world stats, 60s poll, graceful degraded state). A catch-all in `http_app.py` serves the SPA shell for client routes so hard refreshes survive. Scaffolding: react-router, eslint + vitest with component tests, run in CI. Dev verbs: `frontend-install` / `frontend-dev` / `frontend-build` / `frontend-test` / `frontend-lint`.
- **Jobs API** - `src/eco_spec_tracker/`, mounted at `/jobs/api` (public paths `/jobs/api/v1/*` plus `/v1/meta` for the mock-data flag). The jobs UI is the SPA's `/jobs` route consuming this API. Detail: [docs/jobs/FEATURES.md](jobs/FEATURES.md).
- **Sentry telemetry** - one shared idempotent init (`eco_mcp_app/telemetry.py`), DSN via the `SENTRY_DSN` env var from the deploy repo's ExternalSecret.
- **Dev target resolver** - `scripts/resolve-eco-target.sh`, run by the `http` verb to pick the eco game server base URL: LAN mDNS path first (the home router blackholes same-LAN tailnet WireGuard, [infrastructure#294](https://forgejo.coilysiren.me/coilyco-flight-deck/infrastructure/issues/294)), then the SSM-resolved tailnet FQDN, then the public host. An explicit `ECO_INFO_URL` wins outright; `ECO_ADMIN_BASE_URL` / `ECO_MAP_BASE_URL` / `UPSTREAM_URL` (jobs skills endpoint) default to the same base, and `UPSTREAM_API_KEY` is SSM-resolved so local `/jobs` shows real player data, not the mock fallback.

## Local-only components

- **Replay browser** - `src/eco_replay/`, a FastAPI viewer for the replay mod's SQLite event log. Not mounted into the fused service yet. Detail: [docs/replay/README.md](replay/README.md).

## In-game C# plugins (`mods/`)

Server plugins for the Eco game server. Built with the `build-mod-*` ward verbs, shipped to the server out of band.

- **mods/jobs** - skills API plugin (`/api/v1/skills`) the jobs tracker consumes, plus a C# shell harness mirroring the API shape for local dev.
- **mods/replay** - player-action recorder writing the SQLite event log the replay browser reads.
- **mods/telemetry** - logs, metrics, and exception capture inside the game server. Detail: [mods/telemetry/docs/FEATURES.md](../mods/telemetry/docs/FEATURES.md).

## Build and release

- **CI** - `.forgejo/workflows/build-publish.yml`: pytest + ruff + mypy, then docker build and push of `coilysiren-eco-app` to the in-cluster registry. No deploy stage by design.
- **Deploy surface** - lives in `coilyco-bridge/deploy/services/eco-app` (manifests + rollout), per the layer invariant.

## Dropped during consolidation

- The 20M `species_profiles.json` + `ecopedia.json` offline caches, their build scripts, and the `_preload.py` lookup layer that fronted them ([#1](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/1)). Species/ecopedia lookups go straight to the live Wikidata/iNaturalist/Wikipedia paths in `species.py` / `wikidata.py`.
- The per-repo deploy stages and `deploy/main.yml` manifests (moved to the deploy repo, merged to one namespace).

## See also

- [README.md](../README.md) - human-facing intro.
- [AGENTS.md](../AGENTS.md) - agent-facing operating rules.
- [.ward/ward.yaml](../.ward/ward.yaml) - allowlisted commands.

Cross-reference convention from [coilysiren/agentic-os#59](https://github.com/coilyco-flight-deck/agentic-os/issues/59).
