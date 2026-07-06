import { useEffect, useState } from "react"
import { fetchCraftingAtlas } from "../lib/craftingApi"

export interface CraftingPulse {
  crafts: number
  topItem: string | null
}

// Live badge feed for the homepage /crafting card: a one-shot fetch of the
// crafting atlas, folded to the total craft-event count + the most-crafted item.
// Best-effort — a missing or failing endpoint (or an empty atlas) leaves the
// badge absent rather than surfacing an error, the same graceful-degrade
// contract the other homepage pulses keep (eco-app#75).
export function useCraftingPulse(): CraftingPulse | null {
  const [pulse, setPulse] = useState<CraftingPulse | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchCraftingAtlas(controller.signal)
      .then((atlas) => {
        if (controller.signal.aborted || atlas.totalEvents === 0) return
        // byItem was split into byCrafted/byGathered (#70); the badge's
        // "most-crafted item" is the top real-crafted-units entry.
        setPulse({ crafts: atlas.totalEvents, topItem: atlas.byCrafted[0]?.[0] ?? null })
      })
      .catch(() => {
        /* non-fatal: leave the badge absent */
      })
    return () => controller.abort()
  }, [])

  return pulse
}
