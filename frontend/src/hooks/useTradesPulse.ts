import { useEffect, useState } from "react"
import { fetchTradesLedger } from "../lib/tradesApi"

export interface TradesPulse {
  trades: number
  topItem: string | null
}

// Live badge feed for the homepage /trades card: a one-shot fetch of the trades
// ledger, folded to the total trade count + the most-traded item. Best-effort —
// a missing or failing endpoint (or an empty ledger) leaves the badge absent
// rather than surfacing an error, the same graceful-degrade contract the other
// homepage pulses keep (eco-app#75).
export function useTradesPulse(): TradesPulse | null {
  const [pulse, setPulse] = useState<TradesPulse | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchTradesLedger(controller.signal)
      .then((ledger) => {
        if (controller.signal.aborted || ledger.totalTrades === 0) return
        setPulse({ trades: ledger.totalTrades, topItem: ledger.byItem[0]?.[0] ?? null })
      })
      .catch(() => {
        /* non-fatal: leave the badge absent */
      })
    return () => controller.abort()
  }, [])

  return pulse
}
