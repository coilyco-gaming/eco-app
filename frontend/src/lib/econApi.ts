// Typed client for the economy snapshot (/preview/get_eco_economy.json).

export interface EconKpis {
  trades_per_day: number
  trades_total: number
  trades_wow_pct: number
  contract_completion_ratio: number
  contract_failure_rate: number
  contracts_posted: number
  contracts_completed: number
  contracts_failed: number
  loan_default_rate: number
  loans_offered: number
  loans_accepted: number
  loans_repaid: number
  loans_defaulted: number
  wages_total: number
  taxes_paid: number
  govt_funds: number
  net_tax_flow: number
  total_culture: number
}

export interface EconomySnapshot {
  server: { description: string; category: string; sourceUrl: string }
  days_elapsed: number
  admin_ok: boolean
  kpis: EconKpis
  health: string
  narrative: string
  economy_desc: string
}

export async function fetchEconomy(signal?: AbortSignal): Promise<EconomySnapshot> {
  const resp = await fetch("/preview/get_eco_economy.json", { signal })
  if (!resp.ok) {
    throw new Error(`economy fetch failed: HTTP ${resp.status}`)
  }
  return (await resp.json()) as EconomySnapshot
}

// ---------------------------------------------------------------------------
// Money supply / currency roster (/preview/currency.json — the list-mode
// compute_currency_payload from eco_mcp_app/currency.py). This is the richer
// half of the economy view: money supply, active currencies split minted vs
// personal, per-currency trade volume, wealth distribution (top holders), and
// the money/trade time series. Admin-only — series and holders are empty when
// ECO_ADMIN_TOKEN is absent or the stores/economy exporter mod (eco-app#58)
// isn't deployed, and the page degrades section by section.
// ---------------------------------------------------------------------------

export interface MoneyHolder {
  account: string
  holder: string | null
  balance: number
}

export interface MoneyHolders {
  reachable: boolean
  note: string
  accountsCounted: number
  totalHoldings: number
  list: MoneyHolder[]
}

export type CurrencyKind = "minted" | "personal"

export interface CurrencyView {
  name: string
  type: CurrencyKind
  isMinted: boolean
  mintedAmount: number
  mintEvents: number
  tradeCount: number
  tradeVolume: number
  createdBy: string | null
  holders: MoneyHolders
}

// [time, value] samples over in-game seconds.
type Series = Array<[number, number]>

export interface MoneySnapshot {
  mode: string
  days_elapsed: number
  admin_ok: boolean
  narrative: string
  economy_desc: string
  money: {
    activeCurrencies: number
    personalWealth: number
    governmentHoldings: number
    totalSupply: number
    tradeValue7d: number
    hasSupplyData: boolean
  }
  series: {
    personalWealth: Series
    governmentHoldings: Series
    activeCurrencies: Series
    trades7d: Series
  }
  currencies: CurrencyView[]
  minted: CurrencyView[]
  personal: CurrencyView[]
  counts: { total: number; minted: number; personal: number }
  holders_reachable: boolean
  holders_unavailable_note: string
  warnings: string[]
  fetched_at_iso: string
}

// Resolves to null on a missing / failing / wrong-shaped endpoint so the
// money-supply sections degrade on their own, matching fetchCurrency in
// currencyApi.ts. A valid snapshot always carries a `currencies` array.
export async function fetchMoney(signal?: AbortSignal): Promise<MoneySnapshot | null> {
  let resp: Response
  try {
    resp = await fetch("/preview/currency.json", { signal })
  } catch {
    return null
  }
  if (!resp.ok) return null
  let body: unknown
  try {
    body = await resp.json()
  } catch {
    return null
  }
  const snap = body as MoneySnapshot
  if (!snap || !Array.isArray(snap.currencies) || !snap.money) return null
  return snap
}
