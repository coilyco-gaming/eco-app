# Features

Headline-feature inventory for `eco-jobs-tracker`. "What does this repo do," not file-level detail.

## Shape

Three pieces: a C# Eco mod exposing a read-only HTTP endpoint of every player's learned specialties, a FastAPI JSON API doing the row-shaping, and the SPA's `/jobs` page rendering the "who can make what" board. The Jinja2 + HTMX dashboard this package used to serve was retired when the site went fully SPA.

## JSON API (FastAPI)

- **Mounted at `/jobs/api` of the fused service** - public paths `/jobs/api/v1/professions`, `/v1/players`, `/v1/specialties` (unchanged from the Jinja era), plus `/v1/meta` reporting the mock-data flag the SPA's banner reads.
- **Browser UI** - the SPA route `/jobs` (`frontend/src/pages/Jobs.tsx`): stacked Professions (client-side expanders), Specialties, Players sections, plus the recipe-driven "Most valuable to craft" board grouped by profession and ranked by true margin × supply-gap demand. The bundled recipe graph also supplies expandable skill trees from profession root to specialty to level-gated talents ([eco-app#195](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/195)). Old drill-down URLs (`/jobs/professions` etc.) land on the same page via the SPA catch-all.
- **Iframe embedding** - CSP `frame-ancestors` allows `coilysiren.me` to embed; the header now ships site-wide from `eco_mcp_app.http_app` (`FrameAncestorsCSP`).
- **Mock-data fallback** - `UPSTREAM_URL` unset = canned data from `mock_data.py`, flagged via `/v1/meta`.
- **Upstream mod fetch** - `UPSTREAM_URL` set = `upstream.py` calls `/api/v1/skills` with `UPSTREAM_API_KEY` as `X-API-Key`, 5s timeout, no fallback on a dead endpoint.
- **OpenTelemetry exception tracing** - the fused ASGI process records uncaught request exceptions for SigNoz.

## C# Eco mod (`EcoJobsTracker.dll`)

- **`GET /api/v1/skills` endpoint** - ModKit UserCode mod, `[ApiController]` picked up by Eco's ASP.NET host.
- **Every player's learned specialties** - Iterates `UserManager.Users`, filters `Level > 0 && IsSpecialty`, returns name/level/max-level + online state.
- **`GET /api/v1/citizens` endpoint** - Iterates `UserManager.Users` returning `{id, name}`. Exposes the numeric in-game user id the action exporter keys `Citizen` by (the admin `/api/v1/users` surface omits it), so the crafting atlas can join exporter ids to display names ([eco-app#5](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/5)).
- **Auth via Eco's admin-token middleware** - Same `X-API-Key` gate as the rest of `/api/v1/*`. No bespoke auth.
- **Dual-attribute DTOs** - Records carry `System.Text.Json` and `Newtonsoft.Json` camelCase attributes, serializing identically under either pipeline.
- **mod.io distribution** - Listing copy + zip-shape in `mod/modio.md`.

## Shell harness (`mod/shell/`)

- **Standalone ASP.NET mock on `:5100`** - Same routes (`/api/v1/skills`, `/api/v1/citizens`), same DTOs (`<Compile Include>`-linked), canned data. Iterate without booting Eco.

## Deploy and ops

- **Canonical deploy reference for the homelab** - `coilyco-bridge/deploy/services/eco-app` owns manifests and rollout. This repo owns the application image and Ward development surface.
- **k3s + ExternalSecrets** - Pulls `UPSTREAM_API_KEY` from AWS SSM via ClusterSecretStore. OTLP exports over the private network to SigNoz.
- **Image publish** - Builds + pushes to `ghcr.io/coilysiren/eco-spec-tracker/...`, git-SHA tagged.
- **Tailscale + Traefik + cert-manager** - Inherited from `backend` template.
- **Mod package path** - `ward exec package-mods` builds deterministic install-ready ZIPs with the `Mods/EcoJobsTracker/` prefix. `ward exec publish-mod-packages` publishes the immutable package.

## Dev-loop tooling

- **`ward exec sync` / `ward exec http`** - `uv sync --group dev`, then uvicorn with reload on `:4000`.
- **`ward exec run-shell-jobs`** - C# shell harness on `:5100`.
- **`ward exec build-mod-jobs`** - Production mod DLL.
- **`ward exec build-docker`** - Local application image build. Deployment stays in `coilyco-bridge/deploy`.
- **Pre-commit** - ruff + mypy on Python, `dotnet format` on C#.
- **Smoke suite** - `tests/test_smoke.py`: every page, every JSON, parser fixture.

## Naming-debt note

Public name is `eco-jobs-tracker`. Internals still use `eco-spec-tracker` in package and route names. Rename deferred. See README.

## See also

- [README.md](../../README.md) - human-facing intro.
- [AGENTS.md](../../AGENTS.md) - agent-facing operating rules.
- [.ward/ward.yaml](../../.ward/ward.yaml) - allowlisted commands.

Cross-reference convention from [coilysiren/agentic-os#59](https://github.com/coilyco-flight-deck/agentic-os/issues/59).
