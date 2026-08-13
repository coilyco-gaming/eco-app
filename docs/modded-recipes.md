# Modded recipe exports

How eco-app serves a modded server's own recipe graph instead of the bundled
vanilla seed, and — more importantly — how it refuses to pretend it has one.

Built for
[eco-app#179](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/179).

## Why

Recipe and cost surfaces start from a vendored vanilla Eco Gnome export. On a
modded server the recipe graph, output quantities and upgrades differ, so
pricing evidence derived from vanilla is misleading — and misleading in the
worst way, because it looks authoritative.

## The three tiers

`load_recipe_index()` tries them in order:

| Tier | `sourceKind` | Source |
|---|---|---|
| 1 | `modded-export` | The operator-supplied DataExporter export, per server |
| 2 | `autogen` | Parsed from the dedicated server's own AutoGen C# |
| 3 | `vanilla-seed` | The vendored Eco Gnome graph |

Only tier 1 is server-specific. The payload says which one answered:

```jsonc
{
  "sourceKind": "modded-export",
  "source": "DataExporter modded export from Eco via Sirens (version 7, exported 2026-08-13T…)",
  "exportedAtISO": "2026-08-13T…",
  "serverSpecific": true
}
```

`serverSpecific` is the single boolean a pricing consumer needs.

## The failure mode is the point

Any refusal falls back **and says why**, on the payload's `warnings`:

> Serving the vanilla recipe seed: `ECO_MODDED_RECIPE_EXPORT=/path` was exported
> 60.0 days ago, past the 14-day freshness bound. Prices and recipes are NOT
> server-specific.

Refusals: unreadable file, invalid JSON, not DataExporter-shaped (no
`Recipes[]`), an unparseable `ExportedAt`, or an export past the freshness
bound. A stale modded graph is refused rather than trusted, because one that no
longer matches the server is wrong *and* claims to be server-specific.

An export with no `ExportedAt` at all is accepted — the operator pointed at it
deliberately — but the source string says "exported at an unstated time" so
nobody reads it as fresh.

When no export is configured, nothing warns. Vanilla is the correct answer for
a vanilla deploy, and crying wolf on every default install would train readers
to ignore the warning that matters.

## Operator setup

1. Produce a DataExporter export on the Eco server (eco-ops#71 owns this).
2. Mount it read-only into the eco-app pod.
3. Set `ECO_MODDED_RECIPE_EXPORT` to its path.
4. Optionally set `ECO_MODDED_RECIPE_MAX_AGE_DAYS` (default 14).
5. Verify: `/preview/recipes.json` should show `"serverSpecific": true` and name
   your server in `source`.

Refresh the export on the same cadence as the freshness bound, or raise the
bound deliberately. A silently-expiring export degrades to vanilla, which is
safe but not what you wanted.

## Boundaries

**Read-only.** eco-app opens one file the operator names and writes nothing. It
never writes game state, player state, store state, or pricing configuration,
and there is no write-capable game API here.

**No parser fork.** The export goes through the same `build_recipe_index` the
vanilla seed does — both carry `{Version, Skills[], Items[], Tags[],
Recipes[]}`. A modded export needs no separate code path, which is what keeps
this tier cheap to keep working.

**Handoff.** Producing and mounting the export is an operator action.
eco-app's half is the ingestion, the provenance, and the refusals — all of
which ship and are covered by fixture tests. Until an export is mounted, every
response continues to identify itself as the vanilla fallback.
