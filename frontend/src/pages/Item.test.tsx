import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import Item from "./Item"

const PIVOT = {
  fetchedAtISO: "2026-06-12T13:00:00+00:00",
  sourceBaseUrl: "http://x:3001",
  item: "BeetItem",
  trades: [
    {
      tradeType: "CurrencyTrade",
      time: 300000,
      day: 3.47,
      buyer: "rei",
      seller: "coilysiren",
      shopOwner: "coilysiren",
      item: "BeetItem",
      quantity: 2,
      currency: "Credit",
      currencyAmount: 20,
      unitPrice: 10,
      store: "StoreItem",
      location: "1,2,3",
      direction: "sell",
    },
  ],
  crafts: [
    {
      actionType: "HarvestOrHunt",
      time: 250000,
      day: 2.89,
      citizen: "elizacorn",
      station: "(hand)",
      quantity: 10,
    },
  ],
  tradeCount: 1,
  tradeVolume: 20,
  craftCount: 1,
  craftQuantity: 10,
  warnings: [],
}

function stubPivotFetch(payload: unknown = PIVOT) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  )
}

function renderItem(entry = "/item?item=BeetItem") {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Item />
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("Item", () => {
  it("renders the pivot header, a trade line, and a craft line", async () => {
    stubPivotFetch()
    renderItem()

    await waitFor(() => {
      expect(screen.getByTestId("item-pill")).toHaveTextContent("1 trades · 1 made")
    })
    const trade = screen.getByTestId("item-trade-row")
    expect(trade).toHaveTextContent("coilysiren sold 2 Beet to rei @ 10 Credit")
    const craft = screen.getByTestId("item-craft-row")
    expect(craft).toHaveTextContent("elizacorn harvested 10 Beet")
    expect(screen.getByTestId("back-to-items")).toHaveAttribute("href", "/items")
  })

  it("prompts for a selection when no ?item= is present", async () => {
    stubPivotFetch()
    renderItem("/item")

    await waitFor(() => {
      expect(screen.getByTestId("item-missing")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("item-pill")).not.toBeInTheDocument()
  })

  it("shows the empty state for an item with no recorded events", async () => {
    stubPivotFetch({ ...PIVOT, trades: [], crafts: [], tradeCount: 0, craftCount: 0 })
    renderItem()

    await waitFor(() => {
      expect(screen.getByTestId("item-empty")).toBeInTheDocument()
    })
  })

  it("degrades when the pivot fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")))
    renderItem()

    await waitFor(() => {
      expect(screen.getByTestId("item-error")).toBeInTheDocument()
    })
  })
})
