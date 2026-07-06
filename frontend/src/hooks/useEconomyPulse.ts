import { useEffect, useState } from "react"
import { fetchEconomy } from "../lib/econApi"

export interface EconomyPulse {
  tradesPerDay: number
  contracts: number
}

// Live badge feed for the homepage /economy card: a one-shot fetch of the
// economy snapshot, folded to trades-per-day + contracts-posted. Best-effort — a
// missing or failing endpoint (or an empty economy) leaves the badge absent
// rather than surfacing an error, the same graceful-degrade contract the other
// homepage pulses keep (eco-app#75).
export function useEconomyPulse(): EconomyPulse | null {
  const [pulse, setPulse] = useState<EconomyPulse | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchEconomy(controller.signal)
      .then((snapshot) => {
        if (controller.signal.aborted) return
        const { trades_total, trades_per_day, contracts_posted } = snapshot.kpis
        if (trades_total === 0 && contracts_posted === 0) return
        setPulse({ tradesPerDay: trades_per_day, contracts: contracts_posted })
      })
      .catch(() => {
        /* non-fatal: leave the badge absent */
      })
    return () => controller.abort()
  }, [])

  return pulse
}
