import { useEffect, useState } from "react"
import { fetchEcoregion } from "../lib/ecoregionApi"

export interface EcoregionPulse {
  topBiome: string | null
  topMatch: string | null
}

// Live badge feed for the homepage /ecoregion card: a one-shot fetch of the
// ecoregion snapshot, folded to the dominant biome + the closest real-world
// ecoregion match. Best-effort — a missing or failing endpoint (or an empty
// snapshot) leaves the badge absent rather than surfacing an error, the same
// graceful-degrade contract the other homepage pulses keep (eco-app#75).
export function useEcoregionPulse(): EcoregionPulse | null {
  const [pulse, setPulse] = useState<EcoregionPulse | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchEcoregion(controller.signal)
      .then((snapshot) => {
        if (controller.signal.aborted) return
        const topBiome = snapshot.biomes[0]?.display ?? null
        const topMatch = snapshot.ecoregionMatches[0]?.name ?? null
        if (!topBiome && !topMatch) return
        setPulse({ topBiome, topMatch })
      })
      .catch(() => {
        /* non-fatal: leave the badge absent */
      })
    return () => controller.abort()
  }, [])

  return pulse
}
