// Typed client for the logistics board (/preview/logistics.json).
//
// This is the "what should I do" plane: cheapest-source lookups, cross-store
// arbitrage spreads, and supply gaps folded out of the live store offers. The
// backend logistics sibling may not have landed yet — this route can 404 — so
// fetchLogistics resolves to null on a miss and normalises every array so a
// partial payload never crashes the panel (eco-app#54).
//
// Documented contract (frozen here so the SPA can scaffold ahead of the
// backend). All money fields are in the row's own `currency`:
//   cheapestSources[]  { item, itemPretty, store, owner, unitPrice, currency, location }
//   arbitrage[]        { item, itemPretty, currency, buyPrice, buyStore, sellPrice, sellStore, spread, spreadPct }
//   supplyGaps[]       { item, itemPretty, note, demand?, supply? }

import { fetchJsonOrNull } from "./api"

export interface CheapestSource {
  item: string
  itemPretty: string
  store: string
  owner: string
  unitPrice: number
  currency: string
  location: string
}

export interface ArbitrageSpread {
  item: string
  itemPretty: string
  currency: string
  buyPrice: number
  buyStore: string
  sellPrice: number
  sellStore: string
  spread: number
  spreadPct: number
}

export interface SupplyGap {
  item: string
  itemPretty: string
  note: string
  demand?: number
  supply?: number
}

export interface LogisticsBoard {
  view: string
  fetchedAtISO: string
  sourceBaseUrl: string
  cheapestSources: CheapestSource[]
  arbitrage: ArbitrageSpread[]
  supplyGaps: SupplyGap[]
  warnings: string[]
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : []
}

export async function fetchLogistics(signal?: AbortSignal): Promise<LogisticsBoard | null> {
  const body = await fetchJsonOrNull<Partial<LogisticsBoard>>("/preview/logistics.json", signal)
  if (!body) return null
  return {
    view: body.view ?? "logistics",
    fetchedAtISO: body.fetchedAtISO ?? "",
    sourceBaseUrl: body.sourceBaseUrl ?? "",
    cheapestSources: asArray<CheapestSource>(body.cheapestSources),
    arbitrage: asArray<ArbitrageSpread>(body.arbitrage),
    supplyGaps: asArray<SupplyGap>(body.supplyGaps),
    warnings: asArray<string>(body.warnings),
  }
}
