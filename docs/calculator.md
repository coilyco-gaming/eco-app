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
- Initial data comes from a **DataMigrator** that loads a SQLite `ecocraft.db` (vanilla Eco data, `ecocraft/eco_gnome_data.json`) into Postgres.

So self-hosting is a stateful second service, not a static publish. It cannot be baked into eco-app's single Python image, and it needs a build toolchain (the .NET 9 SDK) this repo does not otherwise carry.

## Deploy shape (belongs in coilyco-bridge/deploy)

Per the layer invariant (`infra -> eco-app -> deploy`), the calculator's runtime lands in the deploy repo's `services/eco-app` slot, not here. The new pieces a deploy change needs:

- A **Postgres** for the calculator (a small StatefulSet or a shared instance), with a connection string wired in.
- A **calculator Deployment** running the `mcr.microsoft.com/dotnet/aspnet:9.0` based image built from a fork of eco-gnome-website, with volumes for assets, videos, and dpkeys.
- An **ingress route** onto `eco-app.coilysiren.me`. A subpath like `/calculator` needs Blazor's `<base href>` and the SignalR `_blazor` websocket path handled, so a dedicated host or subdomain is the simpler first cut. The `/calculator` SPA page then links to whatever host the deploy claims.
- The fork itself. Preserve the MIT `LICENSE` and the Eco-Gnome attribution. eco-gnome-website ships no `LICENSE` file despite its MIT README, so a self-host should add one carrying the upstream copyright.

## Phase 2 - Sirens' own numbers

The differentiator is server-accurate pricing. Install the DataExporter mod on the kai-server Eco, export Sirens' modded recipes, skills, and items, and load that into the self-hosted instance in place of the vanilla seed. This needs kai-server access through the eco mod-ops pipeline ([ward#585](https://forgejo.coilysiren.me/coilyco-flight-deck/ward/issues/585) / eco-ops#30) and cannot land until that does.

## House style

Once the self-hosted instance is live, reskin the MudBlazor UI toward eco-app's house style incrementally, a progressive reskin and not a rewrite.

## See also

- [FEATURES.md](FEATURES.md) - where this surface appears in the inventory.
- [#40](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/40) - the tracking issue.
