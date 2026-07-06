import { useEffect, useState } from "react"
import { fetchTradesLedger } from "../lib/tradesApi"

export interface TradesPulse {
  trades: number
  volume: number
  topItem: string | null
}

// Live badge feed for the homepage trade card: a one-shot fetch of the trades
// ledger, folded to the total trade count, total currency volume, and the
// most-traded item. The volume + trade count are the ledger's own aggregates
// (totalCurrencyVolume / totalTrades) — the merged trade card (eco-app#90)
// reads them from here, since the market plane's per-item volumes render empty
// on servers that trade but have no priced markets yet. Best-effort — a missing
// or failing endpoint (or an empty ledger) leaves the badge absent rather than
// surfacing an error, the same graceful-degrade contract the other homepage
// pulses keep (eco-app#75).
export function useTradesPulse(): TradesPulse | null {
  const [pulse, setPulse] = useState<TradesPulse | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchTradesLedger(controller.signal)
      .then((ledger) => {
        if (controller.signal.aborted || ledger.totalTrades === 0) return
        setPulse({
          trades: ledger.totalTrades,
          volume: ledger.totalCurrencyVolume,
          topItem: ledger.byItem[0]?.[0] ?? null,
        })
      })
      .catch(() => {
        /* non-fatal: leave the badge absent */
      })
    return () => controller.abort()
  }, [])

  return pulse
}
