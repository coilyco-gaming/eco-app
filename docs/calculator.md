# The crafting calculator (Eco Gnome)

Eco Gnome (MIT) derives optimal buy and sell prices from a player's professions
and recipes. Upstream is `eco-gnome-website` (C# Blazor plus MudBlazor) and
`eco-gnome-mod`, a server-side DataExporter that dumps a server's modded
recipes.

## What ships now

A homepage card on `/` (`frontend/src/pages/Home.tsx`, `data-testid="dir-gnome"`)
links out to the public Eco Gnome instance with attribution. It was a dedicated
`/calculator` SPA page until the #90 information-architecture cleanup demoted
it to a card.

## Why self-hosting is a second service

The fast path would be publishing its `wwwroot` as static files, but that only
works for Blazor WASM and this is **Blazor Server**: `App.razor` renders with
`@rendermode="@InteractiveServer"`. It also needs **PostgreSQL** through EF
Core and Npgsql, and **persistent volumes** plus data-protection keys, which
the upstream compose file mounts as `app-assets`, `app-videos`, and `app-dpkeys`.
Vanilla item and recipe data ships bundled in the image and imports through the
app's own ImportData path.

So it is a stateful second service, not a static publish, and it cannot be
baked into eco-app's single Python image.

## The deploy slot

Per the layer invariant, the runtime lives in `coilyco-bridge/deploy/services/eco-gnome`:
the **upstream published image** rather than a fork build, a `postgres:17`
Deployment with a `local-path` PVC whose password syncs from SSM through an
ExternalSecret, three more PVCs for the mounts the image expects, and a public
Traefik ingress on its own host, **eco-gnome.coilysiren.me**, because Blazor's
routing does not take a subpath.

MIT and Eco-Gnome attribution are preserved in the slot's `ATTRIBUTION.md`,
since we run their published image rather than vendoring it. Going live is the
standard operator rollout. Phase 2 is feeding it Sirens' own numbers.
