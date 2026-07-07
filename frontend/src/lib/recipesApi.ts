// Typed client for the recipe bill-of-materials plane (eco-app#101), mirroring
// `/preview/recipes.json` — the `RecipeIndex` DTO from `eco_mcp_app/recipes.py`
// (the vendored Eco Gnome recipe graph, eco-app#100).
//
// Unlike the item / trade planes this is ONE static bundled payload — no
// `?server=`, no per-id endpoint. So both the list (/recipes) and the detail
// (/recipe?id=) fetch the same URL, the browser caches it, and the detail page
// resolves a single recipe client-side by `name`.

// One ingredient / product / byproduct entry. `item` is the Eco id
// (`ShaleItem`) or a tag name (`Wood`) when `isTag`; `displayName` is Eco
// Gnome's real en-US name, already prettified server-side.
export interface RecipeComponent {
  item: string
  displayName: string
  quantity: number
  isTag: boolean
}

// The profession gate: skill id + the level the recipe unlocks at.
export interface RecipeSkill {
  name: string
  level: number
}

export interface Recipe {
  name: string
  displayName: string
  product: RecipeComponent
  ingredients: RecipeComponent[]
  byproducts: RecipeComponent[]
  station: string
  stationDisplayName: string
  skill: RecipeSkill | null
  laborCost: number
  craftMinutes: number
  // Null in the vanilla seed — the crafting-table upgrade tier is derived by
  // the cost engine (eco-app#98 C), not carried by the Eco Gnome export. The
  // list page only shows a tier facet once real values land.
  tableTierRequired: number | null
  // Other recipe names in the same FamilyName (alternate ways to craft it).
  variants: string[]
  family: string
  isDefault: boolean
  isBlueprint: boolean
}

// A skill/profession definition — the profession axis for the skill facet.
export interface RecipeSkillDef {
  name: string
  displayName: string
  maxLevel: number
}

export interface RecipeCounts {
  recipes: number
  skills: number
  tags: number
  products: number
  stations: number
}

export interface RecipeIndex {
  fetchedAtISO: string
  source: string
  version: number
  counts: RecipeCounts
  recipes: Recipe[]
  // product item id -> recipe names that produce it (a product can be crafted
  // multiple ways). Powers the "other ways to make this" cross-link.
  byProduct: Record<string, string[]>
  bySkill: Record<string, string[]>
  byStation: Record<string, string[]>
  skills: RecipeSkillDef[]
  // tag name -> associated item ids (a tag ingredient expands to any of these).
  tags: Record<string, string[]>
  warnings: string[]
}

export async function fetchRecipeIndex(signal?: AbortSignal): Promise<RecipeIndex> {
  const resp = await fetch("/preview/recipes.json", { signal })
  if (!resp.ok) {
    throw new Error(`recipe index fetch failed: HTTP ${resp.status}`)
  }
  return (await resp.json()) as RecipeIndex
}
