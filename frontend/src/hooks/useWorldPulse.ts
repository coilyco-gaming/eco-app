import { fetchWorld } from "../lib/worldApi"
import { useFreshData } from "../lib/useFreshData"

export interface WorldPulse {
  events: number
  topCategory: string | null
}

// Goes through the shared refresh contract (eco-app#201) rather than a
// hand-rolled mount-only effect, so a homepage badge on a `live` plane keeps up
// instead of freezing at whatever it read when the tab opened. Best-effort by
// design: any failure leaves the badge absent rather than surfacing an error.

export function useWorldPulse(): WorldPulse | null {
  const { data } = useFreshData("world", async (signal): Promise<WorldPulse | null> => {
    try {
      const world = await fetchWorld(signal)
      if (!world) return null
      return { events: world.totalEvents, topCategory: world.categories[0]?.label ?? null }
    } catch {
      return null
    }
  })
  return data ?? null
}
