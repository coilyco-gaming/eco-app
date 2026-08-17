# Recipes

The recipe graph the cost model and crafting atlas read.

## Primary source: Eco's own AutoGen C#

- **No credential.** `steamcmd +login anonymous +app_update 739590`. Strange
  Loop Games ships the dedicated server anonymously.
- **Carries what Gnome cannot.** A crafting station and a real craft time for
  every recipe, which the community export does not have.
- **Versioned with the server.** The Steam build id rides in the index's
  `source` field, so a recipe set is attributable to a server build.

**Fallback: Eco Gnome.** Where AutoGen is unavailable, the ingested Eco Gnome
export stands in. It is vendored rather than fetched live, for reproducible
builds with no build-time networking, and trimmed to `en-US` while staying
schema-identical: the upstream file is about 6 MB, almost all other locales.

## The DTO (#98)

- **Baseline quantities.** Every quantity is the unmodified `BaseValue`.
- **Product versus byproducts.** `Products[0]` is the primary product, and
  `Products[1:]` are byproducts.
- **Tag ingredients.** An ingredient's `ItemOrTag` is a tag name, such as
  `Wood`, when `isTag` is set.
- **Variants.** Recipes sharing a `FamilyName` are alternate ways to craft the
  same thing.
- **`tableTierRequired` is null.** The export carries no explicit table tier.
- **Graceful empty.** A missing or corrupt bundle yields an empty index with a
  stated reason rather than a crash.

## Surface and phase 2

`/preview/recipes.json` is a single-surface REST data plane: the default
1,453-recipe graph with an optional live cost overlay is a browser payload
rather than a tool result. Phase 2 is server-accurate recipes, reading the
running server rather than a build-time export.

See also: [cost.md](cost.md), [modded-recipes.md](modded-recipes.md).
