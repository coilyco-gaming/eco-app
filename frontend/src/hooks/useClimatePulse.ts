import { fetchClimate } from "../lib/climateApi"
import { useFreshData } from "../lib/useFreshData"

export interface ClimatePulse {
  status: string
  co2Ppm: number | null
}

// Goes through the shared refresh contract (eco-app#201) rather than a
// hand-rolled mount-only effect, so a homepage badge on a `live` plane keeps up
// instead of freezing at whatever it read when the tab opened. Best-effort by
// design: any failure leaves the badge absent rather than surfacing an error.

export function useClimatePulse(): ClimatePulse | null {
  const { data } = useFreshData("climate", async (signal): Promise<ClimatePulse | null> => {
    try {
      const snapshot = await fetchClimate(signal)
      if (snapshot.status === "unknown" && snapshot.co2.current === null) return null
      return { status: snapshot.status, co2Ppm: snapshot.co2.current }
    } catch {
      return null
    }
  })
  return data ?? null
}
