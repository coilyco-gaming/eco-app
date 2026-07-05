// Typed client for the store & trader directory (/preview/stores.json).
//
// The endpoint returns StoreDirectory.to_dict() from eco_mcp_app/stores.py: the
// trades ledger folded into two directories — one row per store (owner,
// location, volume, sell/buy split, top items) and one per trader (name,
// volume, stores operated, top sells/buys). Party ids are already joined to
// names. Resolves to null on a missing / failing endpoint so the /trade page
// degrades panel-by-panel (eco-app#54).

import { fetchJsonOrNull } from "./api"

export interface StoreItemRow {
  item: string
  pretty: string
  tradeCount: number
  volume: number
  quantity: number
  avgUnitPrice: number | null
}

export interface StoreProfile {
  storeKey: string
  label: string
  owner: string
  ownerId: string
  location: string
  storeObject: string
  storeObjectPretty: string
  tradeCount: number
  totalVolume: number
  sellCount: number
  buyCount: number
  uniqueCounterparties: number
  lastDay: number
  // [currency, volume]
  currencies: Array<[string, number]>
  topItems: StoreItemRow[]
  topCounterparties: string[]
}

export interface TraderProfile {
  name: string
  citizenId: string
  tradeCount: number
  totalVolume: number
  sellVolume: number
  buyVolume: number
  uniqueCounterparties: number
  lastDay: number
  storesOperated: Array<Record<string, unknown>>
  topSells: StoreItemRow[]
  topBuys: StoreItemRow[]
}

export interface StoreDirectory {
  view: string
  fetchedAtISO: string
  sourceBaseUrl: string
  totalTrades: number
  perTypeCounts: Record<string, number>
  stores: StoreProfile[]
  traders: TraderProfile[]
  totalStores: number
  totalTraders: number
  warnings: string[]
}

export async function fetchStores(signal?: AbortSignal): Promise<StoreDirectory | null> {
  const body = await fetchJsonOrNull<StoreDirectory>("/preview/stores.json", signal)
  if (!body || !Array.isArray(body.stores)) return null
  return body
}
