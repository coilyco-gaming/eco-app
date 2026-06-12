// Typed client for the crafting atlas (/preview/get_eco_crafting_atlas.json).
// byCitizen ships empty until exporter citizen attribution is fixed (eco-app#5).

export interface CraftingAtlas {
  fetchedAtISO: string
  sourceBaseUrl: string
  totalEvents: number
  byItem: Array<[string, number]>
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
