import { useEffect, useState } from "react"
import { fetchClimate } from "../lib/climateApi"

export interface ClimatePulse {
  status: "stable" | "warming" | "critical" | "unknown"
  co2Ppm: number | null
}

// Live badge feed for the homepage /climate card: a one-shot fetch of the
// climate snapshot, folded to the headline status + current CO2 ppm. Best-effort
// — a missing or failing endpoint (or an unknown/empty snapshot) leaves the
// badge absent rather than surfacing an error, the same graceful-degrade
// contract the other homepage pulses keep (eco-app#75).
export function useClimatePulse(): ClimatePulse | null {
  const [pulse, setPulse] = useState<ClimatePulse | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchClimate(controller.signal)
      .then((snapshot) => {
        if (controller.signal.aborted) return
        if (snapshot.status === "unknown" && snapshot.co2.current === null) return
        setPulse({ status: snapshot.status, co2Ppm: snapshot.co2.current })
      })
      .catch(() => {
        /* non-fatal: leave the badge absent */
      })
    return () => controller.abort()
  }, [])

  return pulse
}
