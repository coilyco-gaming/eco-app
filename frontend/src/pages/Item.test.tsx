import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import Item from "./Item"

// A pivot with a compressed feed: a trade (newest), a 3-run craft, and a single
// craft by a second citizen. worldClockS ages events against real "now".
const PIVOT = {
  fetchedAtISO: "2026-06-12T13:00:00+00:00",
  sourceBaseUrl: "http://x:3001",
  item: "MortarItem",
  trades: [],
  crafts: [],
  feed: [
    {
      kind: "trade",
      time: 305000,
      day: 3.53,
      actor: "coilysiren",
      actionType: "CurrencyTrade",
      station: "StoreItem",
      quantity: 2,
      buyer: "rei",
      seller: "coilysiren",
      currency: "Credit",
      unitPrice: 10,
      currencyAmount: 20,
      runCount: 1,
      spanSeconds: 0,
    },
    {
      kind: "craft",
      time: 300000,
      day: 3.47,
      actor: "Reihtnog",
      actionType: "ItemCraftedAction",
      station: "MasonryTableItem",
      quantity: 4,
      buyer: "",
      seller: "",
      currency: "",
      unitPrice: null,
      currencyAmount: 0,
      runCount: 3,
      spanSeconds: 1800,
    },
    {
      kind: "craft",
      time: 100000,
      day: 1.16,
      actor: "elizacorn",
      actionType: "ItemCraftedAction",
      station: "(hand)",
      quantity: 1,
      buyer: "",
      seller: "",
      currency: "",
      unitPrice: null,
      currencyAmount: 0,
      runCount: 1,
      spanSeconds: 0,
    },
  ],
  feedTruncated: false,
  summary: {
    crafters: [
      { name: "Reihtnog", quantity: 12, events: 3 },
      { name: "elizacorn", quantity: 1, events: 1 },
    ],
    supply: {
      storeCount: 1,
      totalQuantity: 8,
      offers: [
        { store: "coilysiren's Store", owner: "coilysiren", price: 10, quantity: 8, currency: "Credit", source: "history" },
      ],
      capped: false,
    },
    demand: {
      storeCount: 1,
      totalQuantity: 5,
      offers: [
        { store: "rei's Stall", owner: "rei", price: 9, quantity: 5, currency: "Credit", source: "history" },
      ],
      capped: false,
    },
    live: false,
  },
  worldClockS: 310000,
  tradeCount: 1,
  tradeVolume: 20,
  craftCount: 4,
  craftQuantity: 13,
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

function renderItem(entry = "/item?item=MortarItem") {
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
  it("renders the summary, the merged feed, and compressed relative-time rows", async () => {
    stubPivotFetch()
    renderItem()

    await waitFor(() => {
      expect(screen.getByTestId("item-pill")).toHaveTextContent("1 trades · 13 made")
    })
    // Actionable summary: crafters, supply, demand.
    expect(screen.getByTestId("item-crafters")).toHaveTextContent("Reihtnog")
    expect(screen.getByTestId("item-supply")).toHaveTextContent("coilysiren's Store")
    expect(screen.getByTestId("item-demand")).toHaveTextContent("rei")

    // Merged feed: a trade line and a compressed craft run.
    const rows = screen.getAllByTestId("item-feed-row")
    expect(rows).toHaveLength(3)
    expect(rows[0]).toHaveTextContent("coilysiren sold 2 Mortar to rei @ 10 Credit")
    expect(rows[1]).toHaveTextContent("Reihtnog crafted 4 Mortar at Masonry Table")
    expect(rows[1]).toHaveTextContent("3 crafts over 30 minutes")
    expect(screen.getByTestId("back-to-items")).toHaveAttribute("href", "/items")
  })

  it("filters the feed by event type", async () => {
    stubPivotFetch()
    renderItem()

    await waitFor(() => {
      expect(screen.getAllByTestId("item-feed-row")).toHaveLength(3)
    })
    fireEvent.change(screen.getByTestId("item-type-filter"), { target: { value: "trade" } })
    const rows = screen.getAllByTestId("item-feed-row")
    expect(rows).toHaveLength(1)
    expect(rows[0]).toHaveTextContent("coilysiren sold 2 Mortar")
  })

  it("honors a ?q= deep link by filtering the feed", async () => {
    stubPivotFetch()
    renderItem("/item?item=MortarItem&q=reihtnog")

    await waitFor(() => {
      expect(screen.getByTestId("item-filter")).toHaveValue("reihtnog")
    })
    const rows = screen.getAllByTestId("item-feed-row")
    expect(rows).toHaveLength(1)
    expect(rows[0]).toHaveTextContent("Reihtnog crafted 4 Mortar")
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
    stubPivotFetch({
      ...PIVOT,
      feed: [],
      tradeCount: 0,
      craftCount: 0,
      summary: { ...PIVOT.summary, crafters: [] },
    })
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
