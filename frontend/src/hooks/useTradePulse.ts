import { fetchMarket } from "../lib/marketApi"
import { useFreshData } from "../lib/useFreshData"

export interface TradePulse {
  markets: number
  totalVolume: number
}

// Goes through the shared refresh contract (eco-app#201) rather than a
// hand-rolled mount-only effect, so a homepage badge on a `live` plane keeps up
// instead of freezing at whatever it read when the tab opened. Best-effort by
// design: any failure leaves the badge absent rather than surfacing an error.

export function useTradePulse(): TradePulse | null {
  const { data } = useFreshData("market", async (signal): Promise<TradePulse | null> => {
    try {
      const market = await fetchMarket(signal)
      if (!market) return null
      return {
        markets: market.markets.length,
        totalVolume: market.markets.reduce((sum, m) => sum + m.totalVolume, 0),
      }
    } catch {
      return null
    }
  })
  return data ?? null
}
