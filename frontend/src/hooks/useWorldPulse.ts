import { useEffect, useState } from "react"
import { fetchWorld } from "../lib/worldApi"

export interface WorldPulse {
  events: number
  topCategory: string | null
}

// Live badge feed for the homepage /world card: a one-shot fetch of the world
// activity plane, folded to a total event count and the busiest category label.
// Best-effort — a missing or failing endpoint leaves the badge absent rather
// than surfacing an error, the same graceful-degrade contract the /world page
// itself keeps (eco-app#62).
export function useWorldPulse(): WorldPulse | null {
  const [pulse, setPulse] = useState<WorldPulse | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchWorld(controller.signal)
      .then((world) => {
        if (!world || controller.signal.aborted) return
        setPulse({
          events: world.totalEvents,
          topCategory: world.categories[0]?.label ?? null,
        })
      })
      .catch(() => {
        /* non-fatal: leave the badge absent */
      })
    return () => controller.abort()
  }, [])

  return pulse
}
