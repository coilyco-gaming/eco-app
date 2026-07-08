// Typed client for the fair-price advisor (/preview/fair_price.json).

import { fetchJsonOrNull } from "./api"

export interface FairPriceResult {
  view: string
  fetchedAtISO: string
  item: string | null
  seriesId: string | null
  displayName: string | null
  displayUnit: string | null
  frequency: string | null
  latestValue: number | null
  latestDate: string | null
  changes: Record<string, number | null>
  changesLabel: string
  narrative: string
  cached: boolean
  error: string | null
  inGameMedian: number | null
  inGameCurrency: string | null
  inGameTrend: string | null
  inGameVerdict: string | null
}

export async function fetchFairPrice(
  item: string,
  signal?: AbortSignal,
): Promise<FairPriceResult | null> {
  const body = await fetchJsonOrNull<FairPriceResult>(
    `/preview/fair_price.json?item=${encodeURIComponent(item)}`,
    signal,
  )
  if (!body || body.view !== "fair_price") return null
  return body
}
