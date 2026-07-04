# Calculator (Eco Gnome self-host)

The calculator surface brings **Eco Gnome** (MIT) onto eco-app. Eco Gnome works out optimal buy and sell prices for Eco items from a player's professions and their recipes. The decision ([#40](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/40)) is to **self-host the existing MIT tool**, fed by Sirens' data, rather than build an Eco-Gnome-style calculator from scratch. Building one would reinvent an MIT wheel, and the mod half that makes it server-accurate already exists.

- **eco-gnome-website** - https://github.com/Eco-Gnome/eco-gnome-website - MIT, C# Blazor + MudBlazor. The calculator itself.
- **eco-gnome-mod** - https://github.com/Eco-Gnome/eco-gnome-mod - a server-side DataExporter that dumps a server's modded recipes, skills, and items. Feeding its output into a self-hosted instance is this feature's differentiator over the public site.
- Public instance today - https://eco-gnome.com - priced against vanilla Eco data.

## What ships now

`frontend/src/pages/Calculator.tsx` is the `/calculator` SPA page: it introduces the tool, links out to the public Eco Gnome instance and the upstream repos, preserves the MIT attribution, and spells out the self-host roadmap. It is the seam the self-hosted instance slots into once the deploy lands. This is the product UX per the repo rule that the browser face is the SPA, not a server-rendered card.

## What self-hosting actually takes

The issue floated a fast path: if Eco Gnome were Blazor **WASM**, its `wwwroot` could be published as static files and served straight from the fused image, needing no deploy change. That path does not exist. Inspecting the upstream:

- The app is **Blazor Server**, not WASM. `Components/App.razor` renders with `@rendermode="@InteractiveServer"`, and `ecocraft.csproj` is `Microsoft.NET.Sdk.Web` on `net9.0` with a `FrameworkReference` to `Microsoft.AspNetCore.App`. It runs as `dotnet ecocraft.dll`, a live ASP.NET Core process, not a static bundle.
- It needs a **PostgreSQL** database. The csproj pulls `Microsoft.EntityFrameworkCore` and `Npgsql.EntityFrameworkCore.PostgreSQL`, carries EF `Migrations/`, and the compose file stands up `postgres:17` with a `ConnectionStrings__DefaultConnection`.
- It needs **persistent volumes** and **data-protection keys**. The upstream `docker-compose.yml` mounts `app-assets`, `app-videos`, and `app-dpkeys`, and `entrypoint.sh` seeds `eco-icons` and `lang` into the assets volume on start.
- Vanilla item/recipe data ships bundled in the image (`ecocraft/eco_gnome_data.json`) and imports through the app's own ImportData path after first boot. (The upstream `DataMigrator`, a SQLite `ecocraft.db` -> Postgres tool, is their internal migration and needs a `.db` the repo does not ship, so it is not our seed path.)

So self-hosting is a stateful second service, not a static publish. It cannot be baked into eco-app's single Python image - but it needs **no build here**: the upstream publishes `ghcr.io/eco-gnome/eco-gnome-website` (and a `-migrator`), so the deploy slot pins that image directly, the open-webui pattern.

## Deploy slot (landed in coilyco-bridge/deploy/services/eco-gnome)

Per the layer invariant (`infra -> eco-app -> deploy`), the calculator's runtime lives in the deploy repo, not here. That slot now exists at [`coilyco-bridge/deploy/services/eco-gnome`](https://forgejo.coilysiren.me/coilyco-bridge/deploy) - a `deploy/main.yml` + `namespace.yml` + `scripts/rollout.sh`, the `services/eco-app` envsubst pattern. What it stands up:

- The **upstream published image**, not a fork build. eco-gnome-website publishes `ghcr.io/eco-gnome/eco-gnome-website` (and a `-migrator`); the deploy pins it by digest, the open-webui pattern. No .NET build, no fork repo needed - eco-app runs the stock upstream UI as-is, permanently.
- A **Postgres** (`postgres:17`) Deployment + a `local-path` PVC, its password synced from SSM `/eco-gnome/postgres-password` by an ExternalSecret into both the DB and the app connection string. The app **self-applies its EF migrations on boot** (with a retry loop while Postgres warms), so no migration Job - a fresh DB schemas itself.
- Three `local-path` PVCs for the volume mounts the image expects: `/app/wwwroot/assets`, `/app/wwwroot/videos`, and `/app/dpkeys` (data-protection keys).
- A public **Traefik ingress** on a dedicated host, **eco-gnome.coilysiren.me** (not an `eco-app.coilysiren.me/calculator` subpath: Blazor's `<base href>` + the SignalR `_blazor` websocket make a subpath deploy fiddly). cert-manager `letsencrypt-production` TLS + ExternalDNS.

The MIT license + Eco-Gnome attribution are preserved in the slot's `ATTRIBUTION.md`, since we run their published image rather than vendoring their source.

### Remaining to go live (operator, on kai-server)

The deploy artifacts are complete; going live is the standard operator rollout, the same boundary every service here has:

1. Put the DB password at SSM `/eco-gnome/postgres-password`.
2. Grant the CD `deployer` SA a RoleBinding in the `coilysiren-eco-gnome` namespace (infra), or roll by hand: `bash services/eco-gnome/scripts/rollout.sh`.
3. After first boot, import vanilla Eco data through the app (the bundled `eco_gnome_data.json`).
4. Point this `/calculator` page's primary link at `https://eco-gnome.coilysiren.me` once it serves.

## Phase 2 - Sirens' own numbers

The differentiator is server-accurate pricing. Install the DataExporter mod on the kai-server Eco, export Sirens' modded recipes, skills, and items, and load that into the self-hosted instance in place of the vanilla seed. This needs kai-server access through the eco mod-ops pipeline ([ward#585](https://forgejo.coilysiren.me/coilyco-flight-deck/ward/issues/585) / eco-ops#30) and cannot land until that does.

## House style

Dropped (July 2026). eco-app keeps the stock upstream Eco Gnome UI permanently - no reskin, no fork. Recorded so the idea is not resurrected.

## See also

- [FEATURES.md](FEATURES.md) - where this surface appears in the inventory.
- [#40](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/40) - the tracking issue.
