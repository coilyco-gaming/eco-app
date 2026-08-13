import { fetchEcoregion } from "../lib/ecoregionApi"
import { useFreshData } from "../lib/useFreshData"

export interface EcoregionPulse {
  topBiome: string | null
  topMatch: string | null
}

// Goes through the shared refresh contract (eco-app#201) rather than a
// hand-rolled mount-only effect, so a homepage badge on a `live` plane keeps up
// instead of freezing at whatever it read when the tab opened. Best-effort by
// design: any failure leaves the badge absent rather than surfacing an error.

export function useEcoregionPulse(): EcoregionPulse | null {
  const { data } = useFreshData("region", async (signal): Promise<EcoregionPulse | null> => {
    try {
      const snapshot = await fetchEcoregion(signal)
      const topBiome = snapshot.biomes[0]?.display ?? null
      const topMatch = snapshot.ecoregionMatches[0]?.name ?? null
      if (!topBiome && !topMatch) return null
      return { topBiome, topMatch }
    } catch {
      return null
    }
  })
  return data ?? null
}
