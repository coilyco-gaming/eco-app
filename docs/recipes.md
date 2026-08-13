# Recipe definitions (bill-of-materials)

The recipe/skill/item definitions eco-app was missing. The **market** half of
the economy (`market.py`, `trades.py`, `logistics.py`, `stores.py`) and the
production-event leaderboard (`crafting.py`) were all here, but there was no
**bill-of-materials** anywhere - no ingredients-in / product-out, no station, no
required skill, no labor/craft-time cost. `crafting.py` counts observed craft
*events* and says so ("never recipe definitions - which aren't exposed over
HTTP"); this surface is the missing counterpart. Keystone of the recipe/pricing
roadmap ([#98](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/98)
follow-up A, [#100](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/100)),
unblocking the recipes page (B), the cost engine (C), value-per-profession (D),
and the pricing page (E).

## Primary source: Eco's own AutoGen C#

Since [#242](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/242) the
graph is parsed from **Eco's own generated C#**, and the Eco Gnome ingest below
is the fallback. Eco's dedicated server ships `Mods/__core__/AutoGen`: one plain
C# file per recipe, item, skill, and tag, emitted from `RecipeTemplate.tt`. It is
the only vanilla source that carries every DTO field at once.

- **No credential.** `steamcmd +login anonymous +app_update 739590`. SLG
  publishes the dedicated server as an anonymous-login depot, so neither a Steam
  account nor a game licence is involved. ~514 MB.
- **Carries what Gnome cannot.** A crafting station and a real craft time for
  every recipe, plus labor in calories, straight from the definitions the server
  runs. Eco Gnome's export has no table tier and is pinned to whatever vanilla
  snapshot upstream bundled.
- **Versioned with the server.** The Steam build id rides in the index's `source`
  string, so a stale graph is visible in any payload rather than silent.

`src/eco_mcp_app/autogen.py` parses the tree; `scripts/autogen_refresh.py`
(`ward exec autogen-refresh`) regenerates `data/eco_autogen_data.json.gz`. Parsing
rather than compiling keeps .NET out of the pipeline entirely — the tree is
machine-generated, so its grammar is a handful of stable shapes. Provenance and
the SLG copyright are recorded in `data/eco_autogen_data.SOURCE.txt`.

Two shapes carry recipes, and the second is the subtle one. A
`class X : RecipeFamily` declares its own labor and craft time. A
`class X : Recipe` is a **tag-product variant** — `SawHardwoodBoards` and
`SawSoftwoodBoards` both satisfying `SawBoardsRecipe` — and declares only its
ingredients, because Eco applies the owning family's cost when it is crafted.
Left unresolved, 365 of 1,487 recipes would report a free, instant craft, so the
parser pushes the family's labor, craft time, and skill onto its variants.

From build 24618181 (Eco 0.13.0): **1,487 recipes / 44 skills / 112 tags / 1,323
products / 68 stations**, zero warnings, every tag ingredient resolvable.

## Fallback: why ingest Eco Gnome rather than dump Eco

**Eco Gnome is itself a recipe exporter**, so eco-app ingests its output instead
of building a bespoke Eco `RecipeManager` dumper
([#40](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/40),
[#98](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/98)). The
`eco-gnome-mod` DataExporter dumps a server's modded recipes/skills/items, and
`eco-gnome-website` bundles a **vanilla** recipe graph at
`ecocraft/eco_gnome_data.json`. The [#105](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/105)
probe confirmed that bundled file is a complete graph in the **identical schema**
the DataExporter emits, fetchable raw from GitHub - so it is the seed, and the
modded export drops in later with no parser change.

## Data source

`data/eco_gnome_data.json` - vendored from `eco-gnome-website`
(`ecocraft/eco_gnome_data.json`, MIT), pinned from `master@28113f2`
(2026-07-04): **1,453 recipes / 1,526 items / 43 skills / 142 tags**.

- **Vendored, not fetched live.** Reproducible builds, no build-time networking,
  no runtime dependency on GitHub or eco-gnome.com. The [#105](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/105)
  probe's recommended path. Packaged into the wheel via `force-include` in
  `pyproject.toml` (as `eco_mcp_app/data/eco_gnome_data.json`), the same
  mechanism `data/ecoregions.json` uses; source checkouts read it from the repo
  root. `recipes._bundled_data_path` mirrors `ecoregion._load_ecoregions_bundled`.
- **`en-US`-trimmed but schema-identical.** The upstream file is ~6 MB, almost
  all of it 23-locale `LocalizedName` blocks eco-app has no use for. The vendored
  copy keeps only the `en-US` locale and leaves **every other key intact**, so it
  is ~2.2 MB and still parses **identically** to a full DataExporter dump - the
  parser reads `LocalizedName["en-US"]` and falls back to the PascalCase-id
  prettifier when a locale row is blank or absent.

Top-level shape: `{ Version, Skills[], Items[], Tags[], Recipes[] }`. A recipe
carries `Name`, `FamilyName`, `LocalizedName`, `CraftMinutes`, `Labor`,
`RequiredSkill` (+ `RequiredSkillLevel`), `CraftingTable`, `Ingredients[]`, and
`Products[]`. Every quantity (`Labor`, `CraftMinutes`, each ingredient/product
`Quantity`) is wrapped as `{ BaseValue, Modifiers[] }`.

## The DTO ([#98](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/98))

`build_recipe_index(raw)` (pure, no I/O) folds the export into:

```
Recipe {
  name, displayName,
  product      { item, displayName, quantity, isTag },
  ingredients  [ { item, displayName, quantity, isTag }, ... ],
  byproducts   [ ... ],           # Products[1:] — the secondary outputs
  station, stationDisplayName,
  skill        { name, level } | null,
  laborCost, craftMinutes,
  tableTierRequired,              # null — see below
  variants     [ recipeName, ... ],
  family, isDefault, isBlueprint,
}
```

wrapped in a `RecipeIndex { recipes[], byProduct, bySkill, byStation, skills[],
tags, counts, version, source, fetchedAtISO, warnings }`.

Mapping decisions worth knowing:

- **Baseline quantities.** Every quantity is the un-modified `BaseValue`. Eco
  Gnome's `Modifiers[]` (skill/talent/module efficiency and speed) are a
  *per-player* concern the cost engine (C) applies on top; the seed is
  deliberately the baseline recipe.
- **product vs byproducts.** `Products[0]` is the primary product; `Products[1:]`
  are byproducts (e.g. Ashlar Shale also yields Crushed Shale).
- **Tag ingredients.** An ingredient's `ItemOrTag` is a tag name (`Wood`) when
  any item carrying that tag will do; `isTag` flags it, and `RecipeIndex.tags`
  maps the tag to its associated item ids so C can expand it. ~789 of the vanilla
  ingredient references are tags.
- **variants.** Recipes sharing a `FamilyName` are alternate ways to craft the
  same thing (different skill/table). `variants` lists the sibling recipe names;
  `byProduct` independently lists every recipe that yields a given item.
- **`tableTierRequired` is `null`.** The export carries no explicit crafting-table
  upgrade tier. The DTO field exists now so the shape is stable for B-E; the cost
  engine (C) will derive it. Left honestly null rather than guessed.
- **Graceful empty.** A missing or corrupt bundle yields an empty index with a
  `warnings` entry rather than a 500, matching the crafting atlas's posture.

## Surface

`/preview/recipes.json` - the SPA's recipe data plane (`recipes.py` →
`http_app.py`). Unlike the other `/preview/*.json` routes it takes **no
`?server=`**: the graph is static bundled vanilla data, not a per-server live
fetch. Optional `?product=` / `?skill=` / `?station=` narrow the returned
`recipes` list while leaving the lookup maps whole (so a page's facet pickers
still populate). The recipes **page** itself is follow-up B; this ticket lands
the data layer only.

Because the source is an immutable bundled file, the cache is a one-line
in-process memo keyed on the resolved path - not the per-`(server, api-key)`
SQLite the streaming CSV consumers need.

## Phase 2 - server-accurate recipes

The vendored seed is vanilla Eco. When the self-host + DataExporter path lands
(ward#585 / eco-ops#30, see [docs/calculator.md](calculator.md)), Sirens' modded
export replaces `data/eco_gnome_data.json` with **no parser rework** -
`build_recipe_index` reads the same `{ Version, Skills, Items, Tags, Recipes }`
shape either way. The `source` string on the index (and on
`/preview/recipes.json`) records which seed a given payload came from.

## See also

- [docs/FEATURES.md](FEATURES.md) - where this sits in the inventory.
- [docs/crafting.md](crafting.md) - the observed-events counterpart.
- [docs/calculator.md](calculator.md) - the Eco Gnome self-host (Phase 2 source).
- [#98](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/98) - the roadmap epic; [#100](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/100) - this ticket; [#105](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/105) - the data-availability probe.
