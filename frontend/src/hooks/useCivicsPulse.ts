import { fetchCivics } from "../lib/civicsApi"
import { useFreshData } from "../lib/useFreshData"

export interface CivicsPulse {
  events: number
  turnoutPct: number | null
}

// Goes through the shared refresh contract (eco-app#201) rather than a
// hand-rolled mount-only effect, so a homepage badge on a `live` plane keeps up
// instead of freezing at whatever it read when the tab opened. Best-effort by
// design: any failure leaves the badge absent rather than surfacing an error.

export function useCivicsPulse(): CivicsPulse | null {
  const { data } = useFreshData("civics", async (signal): Promise<CivicsPulse | null> => {
    try {
      const report = await fetchCivics(signal)
      if (report.totalEvents === 0) return null
      return {
        events: report.totalEvents,
        turnoutPct: report.turnoutRate !== null ? Math.round(report.turnoutRate * 100) : null,
      }
    } catch {
      return null
    }
  })
  return data ?? null
}
