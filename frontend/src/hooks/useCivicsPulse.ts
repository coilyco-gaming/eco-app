import { useEffect, useState } from "react"
import { fetchCivics } from "../lib/civicsApi"

export interface CivicsPulse {
  events: number
  turnoutPct: number | null
}

// Live badge feed for the homepage /civics card: a one-shot fetch of the civics
// report, folded to a civic-event count and turnout percentage. Best-effort — a
// missing or failing endpoint leaves the badge absent rather than surfacing an
// error, the same graceful-degrade contract the /civics page itself keeps
// (eco-app#61).
export function useCivicsPulse(): CivicsPulse | null {
  const [pulse, setPulse] = useState<CivicsPulse | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchCivics(controller.signal)
      .then((report) => {
        if (controller.signal.aborted || report.totalEvents === 0) return
        setPulse({
          events: report.totalEvents,
          turnoutPct: report.turnoutRate !== null ? Math.round(report.turnoutRate * 100) : null,
        })
      })
      .catch(() => {
        /* non-fatal: leave the badge absent */
      })
    return () => controller.abort()
  }, [])

  return pulse
}
