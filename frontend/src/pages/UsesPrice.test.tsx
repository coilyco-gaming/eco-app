import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import UsesPrice from "./UsesPrice"

const MARKET = {
  view: "market",
  fetchedAtISO: "2026-07-07T13:00:00+00:00",
  sourceBaseUrl: "http://x:3001",
  totalTrades: 12,
  markets: [
    {
      item: "IronIngotItem",
      itemPretty: "Iron Ingot",
      currency: "Credit",
      buckets: [
        { day: 1, median: 8, min: 7, max: 9, volume: 12, trades: 3 },
        { day: 2, median: 10, min: 9, max: 11, volume: 15, trades: 4 },
      ],
      medianPrice: 9,
      latestPrice: 10,
      latestDay: 2,
      trend: "rising",
      trendDeltaPct: 11.1,
      shortMedian: 10,
      longMedian: 9,
      totalVolume: 27,
      totalTrades: 7,
    },
  ],
  warnings: [],
}

const LOGISTICS = {
  view: "logistics",
  fetchedAtISO: "2026-07-07T13:00:00+00:00",
  sourceBaseUrl: "http://x:3001",
  live: true,
  totalOffers: 4,
  totalStores: 2,
  cheapest: [
    {
      item: "IronIngotItem",
      itemPretty: "Iron Ingot",
      currency: "Credit",
      sellerCount: 2,
      buyerCount: 0,
      cheapest: 8,
      offers: [
        {
          store: "North Market",
          owner: "Ava",
          storeKey: "north",
          item: "IronIngotItem",
          itemPretty: "Iron Ingot",
          currency: "Credit",
          side: "sell",
          price: 8,
          quantity: 10,
          source: "live",
          lastDay: 2,
        },
      ],
    },
  ],
  resale: [
    {
      item: "IronIngotItem",
      itemPretty: "Iron Ingot",
      currency: "Credit",
      sellerCount: 0,
      buyerCount: 2,
      best: 11,
      offers: [
        {
          store: "Forge",
          owner: "Bo",
          storeKey: "forge",
          item: "IronIngotItem",
          itemPretty: "Iron Ingot",
          currency: "Credit",
          side: "buy",
          price: 11,
          quantity: 6,
          source: "history",
          lastDay: 2,
        },
      ],
    },
  ],
  arbitrage: [],
  supplyGaps: [],
  warnings: [],
}

const FAIR_PRICE = {
  view: "fair_price",
  fetchedAtISO: "2026-07-07T13:00:00+00:00",
  item: "IronIngot",
  seriesId: "PIORECRUSDM",
  displayName: "iron ore",
  displayUnit: "USD / metric ton",
  frequency: "M",
  latestValue: 120,
  latestDate: "2026-07-01",
  changes: { "1m": 5, "3m": 10, "12m": 20 },
  changesLabel: "monthly",
  narrative: "Real iron ore: 120 USD / metric ton.",
  cached: false,
  error: null,
  inGameMedian: 9,
  inGameCurrency: "Credit",
  inGameTrend: "rising",
  inGameVerdict: "fair",
}

const RECIPE_COST = {
  fetchedAtISO: "2026-07-07T13:00:00+00:00",
  warnings: [],
  costParams: { caloriePrice: 0, minutePrice: 0 },
  recipes: [
    {
      name: "IronIngotRecipe",
      displayName: "Iron Ingot",
      product: { item: "IronIngotItem", displayName: "Iron Ingot", quantity: 1 },
      cost: {
        recipe: "IronIngotRecipe",
        product: "IronIngotItem",
        yield: 1,
        perUnitCost: 6.5,
        totalCost: 6.5,
        ingredientCost: 5,
        laborCost: 1,
        timeCost: 0.5,
        laborCalories: 100,
        craftMinutes: 1,
        complete: true,
        unpricedInputs: [],
        ingredients: [
          {
            item: "IronOreItem",
            displayName: "Iron Ore",
            quantity: 1,
            isTag: false,
            unitCost: 5,
            source: "market",
            subtotal: 5,
          },
        ],
      },
    },
  ],
}

function stubFetch(route: {
  market?: unknown
  logistics?: unknown
  fairPrice?: unknown
  recipes?: unknown
  marketOk?: boolean
  logisticsOk?: boolean
  fairPriceOk?: boolean
  recipesOk?: boolean
}) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      if (url.includes("/preview/market.json")) {
        return Promise.resolve(
          new Response(JSON.stringify(route.market ?? {}), {
            status: route.marketOk === false ? 404 : 200,
            headers: { "Content-Type": "application/json" },
          }),
        )
      }
      if (url.includes("/preview/logistics.json")) {
        return Promise.resolve(
          new Response(JSON.stringify(route.logistics ?? {}), {
            status: route.logisticsOk === false ? 404 : 200,
            headers: { "Content-Type": "application/json" },
          }),
        )
      }
      if (url.includes("/preview/fair_price.json")) {
        return Promise.resolve(
          new Response(JSON.stringify(route.fairPrice ?? {}), {
            status: route.fairPriceOk === false ? 404 : 200,
            headers: { "Content-Type": "application/json" },
          }),
        )
      }
      if (url.includes("/preview/recipes.json")) {
        return Promise.resolve(
          new Response(JSON.stringify(route.recipes ?? {}), {
            status: route.recipesOk === false ? 404 : 200,
            headers: { "Content-Type": "application/json" },
          }),
        )
      }
      return Promise.resolve(new Response("{}", { status: 404 }))
    }),
  )
}

function renderPage(entry = "/uses/price") {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <UsesPrice />
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("UsesPrice", () => {
  it("lists candidate items when no item is selected", async () => {
    stubFetch({ market: MARKET, logistics: LOGISTICS, fairPrice: FAIR_PRICE, recipes: RECIPE_COST })
    renderPage()

    await waitFor(() => {
      expect(screen.getByTestId("price-picker")).toBeInTheDocument()
    })
    expect(screen.getAllByTestId("pick-item")[0]).toHaveTextContent("Iron Ingot")
  })

  it("renders the market, shelf, fair-price, and craft-cost panels for a selected item", async () => {
    stubFetch({ market: MARKET, logistics: LOGISTICS, fairPrice: FAIR_PRICE, recipes: RECIPE_COST })
    renderPage("/uses/price?item=IronIngotItem")

    await waitFor(() => {
      expect(screen.getByTestId("price-band-table")).toBeInTheDocument()
    })
    expect(screen.getByTestId("price-pill")).toHaveTextContent("9 Credit median")
    expect(screen.getByTestId("price-band-pill")).toHaveTextContent("IQR")
    expect(screen.getByTestId("price-fred")).toHaveTextContent("iron ore benchmark")
    expect(screen.getByTestId("price-trend")).toHaveTextContent("rising")
    expect(screen.getByTestId("price-comparison-table")).toBeInTheDocument()
    expect(screen.getByTestId("price-cost-table")).toBeInTheDocument()
    expect(screen.getByTestId("price-suggestion-list")).toHaveTextContent("Target ask")
    expect(within(screen.getByTestId("price-comparison-table")).getAllByTestId("price-sell-row")).toHaveLength(1)
  })

  it("shows the cost-model-pending note when the recipe plane is missing", async () => {
    stubFetch({
      market: MARKET,
      logistics: LOGISTICS,
      fairPrice: FAIR_PRICE,
      recipes: {},
      recipesOk: false,
    })
    renderPage("/uses/price?item=IronIngotItem")

    await waitFor(() => {
      expect(screen.getByTestId("price-cost-pending")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("price-cost-table")).not.toBeInTheDocument()
  })

  it("degrades the shelf comparison independently when logistics is unavailable", async () => {
    stubFetch({
      market: MARKET,
      logistics: {},
      fairPrice: FAIR_PRICE,
      recipes: RECIPE_COST,
      logisticsOk: false,
    })
    renderPage("/uses/price?item=IronIngotItem")

    await waitFor(() => {
      expect(screen.getByTestId("price-market-band")).toBeInTheDocument()
    })
    expect(screen.getByTestId("price-comparison-empty")).toBeInTheDocument()
    expect(screen.queryByTestId("price-comparison-table")).not.toBeInTheDocument()
  })
})
