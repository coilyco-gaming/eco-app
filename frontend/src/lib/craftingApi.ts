// Typed client for the crafting atlas (/preview/get_eco_crafting_atlas.json).
// byCitizen carries display names joined from the jobs mod's /api/v1/citizens
// surface, falling back to "Citizen #<id>" when a name is missing (eco-app#5).
//
// Produced items are split into two boards (eco-app#70): byCrafted counts real
// crafted units (ItemCraftedAction), byGathered counts harvest/chop/dig *events*
// (their raw Count is biomass magnitude, not a unit count, so summing it buried
// player crafting under plant biomass). byStation / byCitizen are event counts.

export interface CraftingAtlas {
  fetchedAtISO: string
  sourceBaseUrl: string
  totalEvents: number
  byCrafted: Array<[string, number]>
  byGathered: Array<[string, number]>
  byStation: Array<[string, number]>
  byCitizen: Array<[string, number]>
  flows: Array<[string, string, number]>
  perActionCounts: Record<string, number>
  warnings: string[]
}

export async function fetchCraftingAtlas(signal?: AbortSignal): Promise<CraftingAtlas> {
  const resp = await fetch("/preview/get_eco_crafting_atlas.json", { signal })
  if (!resp.ok) {
    throw new Error(`crafting atlas fetch failed: HTTP ${resp.status}`)
  }
  return (await resp.json()) as CraftingAtlas
}
