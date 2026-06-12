# eco-app features

Living inventory of what ships from this monorepo. Component-level detail lives in the per-component docs linked below, which were carried over from the four source repos during the consolidation ([coilysiren/inbox#101](https://forgejo.coilysiren.me/coilysiren/inbox/issues/101)).

## The fused service

One image, one uvicorn process, entrypoint `eco_mcp_app.http_app:app` on port 4000.

- **MCP server** - `src/eco_mcp_app/`, the core. Stdio for Claude Desktop, Streamable-HTTP at `/mcp/` for URL-connected hosts, browser preview surface at `/preview/*`. Full tool/resource inventory: [docs/mcp/FEATURES.md](mcp/FEATURES.md).
- **React frontend** - `frontend/`, a Vite + React + TypeScript SPA (no SSR). The Docker image builds it in a node stage and the fused service serves it at `/` (assets under `/assets`); a checkout without a build keeps the old `/` -> `/preview` redirect. Placeholder landing page today, the eco-app.coilysiren.me site as it iterates. Dev verbs: `frontend-install` / `frontend-dev` / `frontend-build`.
- **Jobs tracker** - `src/eco_spec_tracker/`, mounted at `/jobs`. Jinja2 + HTMX UI over player professions and specialties plus a JSON API. Detail: [docs/jobs/FEATURES.md](jobs/FEATURES.md).
- **Sentry telemetry** - one shared idempotent init (`eco_mcp_app/telemetry.py`), DSN via the `SENTRY_DSN` env var from the deploy repo's ExternalSecret.

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

- The 20M `species_profiles.json` + `ecopedia.json` offline caches and their build scripts. Species/ecopedia lookups now go straight to the live Wikidata/iNaturalist/Wikipedia fallback paths in `src/eco_mcp_app/_preload.py`.
- The per-repo deploy stages and `deploy/main.yml` manifests (moved to the deploy repo, merged to one namespace).

## See also

- [README.md](../README.md) - human-facing intro.
- [AGENTS.md](../AGENTS.md) - agent-facing operating rules.
- [.ward/ward.yaml](../.ward/ward.yaml) - allowlisted commands.

Cross-reference convention from [coilysiren/agentic-os#59](https://github.com/coilyco-flight-deck/agentic-os/issues/59).
