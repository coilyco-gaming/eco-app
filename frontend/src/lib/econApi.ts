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
