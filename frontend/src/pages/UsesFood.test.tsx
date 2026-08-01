import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import UsesFood from "./UsesFood"

const REPORT = {
  view: "food_signals",
  fetchedAtISO: "2026-08-01T00:00:00+00:00",
  sourceBaseUrl: "http://eco.example",
  foodCount: 2,
  warnings: [],
  signals: [
    { item: "CookedCornItem", itemPretty: "Cooked Corn", signal: "restock", reason: "Live shelves show 25 units wanted with 0 supplied.", live: true, supplyQty: 0, demandQty: 25, tradeCount: 4, craftCount: 10 },
    { item: "CharredTomatoItem", itemPretty: "Charred Tomato", signal: "insufficient", reason: "No live shelf observation is available for this confirmed food item.", live: false, supplyQty: 0, demandQty: 0, tradeCount: 0, craftCount: 3 },
  ],
}

function renderPage() {
  return render(<MemoryRouter initialEntries={["/uses/food"]}><UsesFood /></MemoryRouter>)
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("UsesFood", () => {
  it("shows confirmed food signals with evidence and deep links", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(REPORT))))
    renderPage()
    await waitFor(() => expect(screen.getByTestId("food-list")).toBeInTheDocument())
    expect(screen.getAllByTestId("food-row")).toHaveLength(2)
    expect(screen.getAllByTestId("food-signal")[0]).toHaveTextContent("restock")
    const firstRow = screen.getAllByTestId("food-row")[0]
    expect(firstRow.querySelector('a[href="/trade?q=CookedCornItem"]')).toBeInTheDocument()
    expect(firstRow.querySelector('a[href="/uses/price?item=CookedCornItem"]')).toBeInTheDocument()
  })

  it("degrades when the food data plane is unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 404 })))
    renderPage()
    await waitFor(() => expect(screen.getByTestId("food-unavailable")).toBeInTheDocument())
  })
})
