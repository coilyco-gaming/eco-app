import { fetchJsonOrNull } from "./api"

export type FoodSignalKind = "restock" | "balanced" | "potential_overstock" | "insufficient"

export interface FoodSignal {
  item: string
  itemPretty: string
  signal: FoodSignalKind
  reason: string
  live: boolean
  supplyQty: number
  demandQty: number
  tradeCount: number
  craftCount: number
}

export interface FoodReport {
  view: "food_signals"
  fetchedAtISO: string
  sourceBaseUrl: string
  foodCount: number
  signals: FoodSignal[]
  warnings: string[]
}

export async function fetchFoodReport(signal?: AbortSignal): Promise<FoodReport | null> {
  return await fetchJsonOrNull<FoodReport>("/preview/food.json", signal)
}
