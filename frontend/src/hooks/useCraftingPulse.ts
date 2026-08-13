import { fetchCraftingAtlas } from "../lib/craftingApi"
import { useFreshData } from "../lib/useFreshData"

export interface CraftingPulse {
  crafts: number
  topItem: string | null
}

// Goes through the shared refresh contract (eco-app#201) rather than a
// hand-rolled mount-only effect, so a homepage badge on a `live` plane keeps up
// instead of freezing at whatever it read when the tab opened. Best-effort by
// design: any failure leaves the badge absent rather than surfacing an error.

export function useCraftingPulse(): CraftingPulse | null {
  const { data } = useFreshData("crafting", async (signal): Promise<CraftingPulse | null> => {
    try {
      const atlas = await fetchCraftingAtlas(signal)
      if (atlas.totalEvents === 0) return null
      return { crafts: atlas.totalEvents, topItem: atlas.byCrafted?.[0]?.[0] ?? null }
    } catch {
      return null
    }
  })
  return data ?? null
}
