import { useEffect, useState } from "react"
import { fetchMarket } from "../lib/marketApi"

export interface TradePulse {
  markets: number
  totalVolume: number
}

// Live badge feed for the homepage /trade card: a one-shot fetch of the market
// plane, folded to a market count and total volume. Best-effort — a missing or
// failing endpoint leaves the badge absent rather than surfacing an error, the
// same graceful-degrade contract the /trade page itself keeps (eco-app#54).
export function useTradePulse(): TradePulse | null {
  const [pulse, setPulse] = useState<TradePulse | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchMarket(controller.signal)
      .then((market) => {
        if (!market || controller.signal.aborted) return
        setPulse({
          markets: market.markets.length,
          totalVolume: market.markets.reduce((s, m) => s + m.totalVolume, 0),
        })
      })
      .catch(() => {
        /* non-fatal: leave the badge absent */
      })
    return () => controller.abort()
  }, [])

  return pulse
}
