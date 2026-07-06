import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import Trades from "./Trades"

const LEDGER = {
  fetchedAtISO: "2026-06-12T13:00:00+00:00",
  sourceBaseUrl: "http://x:3001",
  totalTrades: 3,
  perTypeCounts: { CurrencyTrade: 3, BarterTrade: 0 },
  totalCurrencyVolume: 615,
  trades: [
    {
      tradeType: "CurrencyTrade",
      time: 300000,
      day: 3.47,
      buyer: "coilysiren",
      seller: "ekans",
      shopOwner: "ekans",
      item: "IronIngotItem",
      quantity: 10,
      currency: "Credit",
      currencyAmount: 250,
      unitPrice: 25,
      store: "StoreItem",
      location: "1,2,3",
      direction: "buy",
    },
    {
      tradeType: "CurrencyTrade",
      time: 200000,
      day: 2.31,
      buyer: "redwood",
      seller: "ekans",
      shopOwner: "ekans",
      item: "IronIngotItem",
      quantity: 5,
      currency: "Credit",
      currencyAmount: 140,
      unitPrice: 28,
      store: "StoreItem",
      location: "1,2,3",
      direction: "buy",
    },
    {
      tradeType: "CurrencyTrade",
      time: 100000,
      day: 1.15,
      buyer: "Citizen #999",
      seller: "coilysiren",
      shopOwner: "coilysiren",
      item: "WheatItem",
      quantity: 45,
      currency: "Credit",
      currencyAmount: 225,
      unitPrice: 5,
      store: "StoreItem",
      location: "4,5,6",
      direction: "sell",
    },
  ],
  byItem: [
    ["IronIngotItem", 2, 390],
    ["WheatItem", 1, 225],
  ],
  byCurrency: [["Credit", 615]],
  topBuyers: [
    ["coilysiren", 250],
    ["redwood", 140],
    ["Citizen #999", 225],
  ],
  topSellers: [
    ["ekans", 390],
    ["coilysiren", 225],
  ],
  priceSeries: {
    IronIngotItem: [
      [2, 28],
      [3, 25],
    ],
  },
  warnings: [],
}

const WATCHERS_REPORT = {
  view: "watcher_hits",
  advanced: false,
  hits: [
    {
      id: "w_abc123",
      kind: "price",
      value: "IronIngotItem",
      op: "under",
      threshold: 2.5,
      label: "cheap iron",
      server: null,
      lastSeen: 0,
      createdAt: 0,
      describe: "Iron Ingot under 2.5",
      feed: [],
      feedCount: 2,
      display: {
        matchCount: 5,
        recent: [],
        bestUnitPrice: 2,
        totalVolume: 40,
        lastMatchTime: 300000,
      },
      newLastSeen: 300000,
    },
  ],
}

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

// The page fires two fetches: the ledger and the watchers report. By default
// both resolve; a URL check routes each to its payload. `watchers` defaults to
// an empty report so the watcher sidebar stays hidden unless a test opts in.
function stubLedgerFetch(payload: unknown = LEDGER, watchers: unknown = { hits: [] }) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      Promise.resolve(
        String(url).includes("/preview/watchers.json")
          ? jsonResponse(watchers)
          : jsonResponse(payload),
      ),
    ),
  )
}

function renderTrades(entry = "/trades") {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Trades />
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("Trades", () => {
  it("renders totals, the ledger rows, and both cross-links", async () => {
    stubLedgerFetch()
    renderTrades()

    await waitFor(() => {
      expect(screen.getByTestId("trades-pill")).toHaveTextContent("3 trades")
    })
    expect(screen.getByTestId("trades-pill")).toHaveTextContent("615 currency moved")
    // One row per trade.
    expect(screen.getAllByTestId("trade-row")).toHaveLength(3)
    // Prettified item names show in the ledger.
    expect(screen.getAllByText("Iron Ingot").length).toBeGreaterThan(0)
    expect(screen.getByTestId("link-trade")).toHaveAttribute("href", "/trade")
    expect(screen.getByTestId("link-crafting")).toHaveAttribute("href", "/crafting")
  })

  it("ranks top sellers and buyers by currency", async () => {
    stubLedgerFetch()
    renderTrades()

    await waitFor(() => {
      expect(screen.getAllByTestId("trader-row").length).toBeGreaterThan(0)
    })
    // ekans is the top seller (390 earned) — appears in the trader list and
    // in the ledger's seller column, so match on any occurrence.
    expect(screen.getAllByText("ekans").length).toBeGreaterThan(0)
    // Unmapped ids keep their "Citizen #<id>" label verbatim.
    expect(screen.getAllByText("Citizen #999").length).toBeGreaterThan(0)
  })

  it("charts price over time for the busiest priced item", async () => {
    stubLedgerFetch()
    renderTrades()

    await waitFor(() => {
      expect(screen.getByTestId("price-chart")).toBeInTheDocument()
    })
    expect(screen.getByText(/Price over time — Iron Ingot/)).toBeInTheDocument()
  })

  it("honors a ?q= deep link by filtering the ledger", async () => {
    stubLedgerFetch()
    renderTrades("/trades?q=wheat")

    await waitFor(() => {
      expect(screen.getByTestId("trades-filter")).toHaveValue("wheat")
    })
    // Only the WheatItem trade survives the filter.
    expect(screen.getAllByTestId("trade-row")).toHaveLength(1)
    expect(screen.getByText("Wheat")).toBeInTheDocument()
  })

  it("pushes an item cell click into the filter", async () => {
    stubLedgerFetch()
    renderTrades()

    await waitFor(() => {
      expect(screen.getAllByTestId("trade-row")).toHaveLength(3)
    })
    fireEvent.click(screen.getByText("Wheat"))
    expect(screen.getByTestId("trades-filter")).toHaveValue("Wheat")
    expect(screen.getAllByTestId("trade-row")).toHaveLength(1)
  })

  it("shows an empty state when no trades are recorded", async () => {
    stubLedgerFetch({ ...LEDGER, totalTrades: 0, trades: [], byItem: [], priceSeries: {} })
    renderTrades()

    await waitFor(() => {
      expect(screen.getByTestId("trades-empty")).toBeInTheDocument()
    })
  })

  it("degrades when the ledger fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")))
    renderTrades()

    await waitFor(() => {
      expect(screen.getByTestId("trades-error")).toBeInTheDocument()
    })
  })

  it("shows the trade-watcher sidebar with a feed badge when watchers exist", async () => {
    stubLedgerFetch(LEDGER, WATCHERS_REPORT)
    renderTrades()

    await waitFor(() => {
      expect(screen.getByTestId("watchers-section")).toBeInTheDocument()
    })
    expect(screen.getByTestId("watcher-row")).toHaveTextContent("cheap iron")
    // Current matching state (display semantic).
    expect(screen.getByTestId("watcher-row")).toHaveTextContent("5 match")
    // New-since-last-check count (feed semantic).
    expect(screen.getByTestId("watcher-badge")).toHaveTextContent("+2 new")
  })

  it("hides the watcher sidebar when the store is empty", async () => {
    stubLedgerFetch()
    renderTrades()

    await waitFor(() => {
      expect(screen.getAllByTestId("trade-row")).toHaveLength(3)
    })
    expect(screen.queryByTestId("watchers-section")).not.toBeInTheDocument()
  })
})
