// Typed client for the trades ledger (/preview/get_trades.json).
//
// The endpoint returns TradesLedger.to_dict() from eco_mcp_app/trades.py: the
// row-level detailed trades (newest first, capped) plus the aggregates that
// fall out of them — top buyers/sellers by currency, per-currency volume,
// most-traded items, and a per-item price-over-time series. Party ids are
// already joined to names (Buyer/Seller/ShopOwner), falling back to
// "Citizen #<id>" when the jobs-mod citizens join misses one (eco-app#5).

export interface Trade {
  tradeType: string
  time: number
  day: number
  buyer: string
  seller: string
  shopOwner: string
  item: string
  quantity: number
  currency: string
  currencyAmount: number
  unitPrice: number | null
  store: string
  location: string
  direction: string
  eventCount?: number
  aggregated?: boolean
}

export interface TradesLedger {
  fetchedAtISO: string
  sourceBaseUrl: string
  totalTrades: number
  detailedTrades?: number
  rollupRows?: number
  rollupTrades?: number
  perTypeCounts: Record<string, number>
  trades: Trade[]
  totalCurrencyVolume: number
  // [item, tradeCount, currencyVolume]
  byItem: Array<[string, number, number]>
  // [currency, totalAmount]
  byCurrency: Array<[string, number]>
  // [name, currencySpent] / [name, currencyEarned]
  topBuyers: Array<[string, number]>
  topSellers: Array<[string, number]>
  // item -> [[day, meanUnitPrice], ...]
  priceSeries: Record<string, Array<[number, number]>>
  warnings: string[]
}

export async function fetchTradesLedger(signal?: AbortSignal): Promise<TradesLedger> {
  // limit=0: the SPA renders the full set; the bounded default exists for
  // MCP callers, who have a response cap the browser does not (eco-app#256).
  const resp = await fetch("/preview/get_trades.json?limit=0", { signal })
  if (!resp.ok) {
    throw new Error(`trades ledger fetch failed: HTTP ${resp.status}`)
  }
  return (await resp.json()) as TradesLedger
}
