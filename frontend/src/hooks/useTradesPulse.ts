import { fetchTradesLedger } from "../lib/tradesApi"
import { useFreshData } from "../lib/useFreshData"

export interface TradesPulse {
  trades: number
  volume: number
  topItem: string | null
}

// Goes through the shared refresh contract (eco-app#201) rather than a
// hand-rolled mount-only effect, so a homepage badge on a `live` plane keeps up
// instead of freezing at whatever it read when the tab opened. Best-effort by
// design: any failure leaves the badge absent rather than surfacing an error.

export function useTradesPulse(): TradesPulse | null {
  const { data } = useFreshData("trades", async (signal): Promise<TradesPulse | null> => {
    try {
      const ledger = await fetchTradesLedger(signal)
      if (ledger.totalTrades === 0) return null
      return {
        trades: ledger.totalTrades,
        volume: ledger.totalCurrencyVolume,
        topItem: ledger.byItem[0]?.[0] ?? null,
      }
    } catch {
      return null
    }
  })
  return data ?? null
}
