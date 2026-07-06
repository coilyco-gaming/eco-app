import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import Home from "./Home"
import { SAMPLE_STATUS } from "../test/fixtures"

function renderHome() {
  return render(
    <MemoryRouter>
      <Home />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe("Home", () => {
  it("renders the directory with live badges", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(SAMPLE_STATUS), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    )

    renderHome()

    expect(screen.getByTestId("dir-server")).toHaveAttribute("href", "/server")
    expect(screen.getByTestId("dir-jobs")).toHaveAttribute("href", "/jobs")

    await waitFor(() => {
      expect(screen.getByTestId("server-badges")).toHaveTextContent("3d to meteor")
    })
    expect(screen.getByTestId("server-badges")).toHaveTextContent("1 online")
    expect(screen.getByRole("link", { name: "Join the Discord" })).toHaveAttribute(
      "href",
      "https://discord.gg/example",
    )
  })

  it("renders per-surface sub-card badges from the live pulse endpoints", async () => {
    const byUrl: Record<string, unknown> = {
      "/preview.json": SAMPLE_STATUS,
      "/preview/get_eco_economy.json": {
        kpis: { trades_total: 1341, trades_per_day: 24, contracts_posted: 8 },
      },
      "/preview/get_eco_trades.json": {
        totalTrades: 1341,
        byItem: [["BunWulfRawMeatItem", 90, 400]],
      },
      "/preview/get_eco_crafting_atlas.json": {
        totalEvents: 512,
        byItem: [["WoodenChairItem", 40]],
      },
      "/preview/get_eco_climate.json": {
        status: "warming",
        co2: { current: 620 },
      },
      "/preview/get_eco_ecoregion.json": {
        biomes: [{ display: "Grassland" }],
        ecoregionMatches: [{ name: "Serengeti" }],
      },
    }

    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input.toString()
        const key = Object.keys(byUrl).find((u) => url.includes(u))
        const body = key ? byUrl[key] : {}
        return Promise.resolve(
          new Response(JSON.stringify(body), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        )
      }),
    )

    renderHome()

    await waitFor(() => {
      expect(screen.getByTestId("economy-badges")).toHaveTextContent("24 trades/day")
    })
    expect(screen.getByTestId("economy-badges")).toHaveTextContent("8 contracts")
    expect(screen.getByTestId("trades-badges")).toHaveTextContent("1,341 trades")
    expect(screen.getByTestId("trades-badges")).toHaveTextContent("top: Bun Wulf Raw Meat")
    expect(screen.getByTestId("crafting-badges")).toHaveTextContent("512 crafts")
    expect(screen.getByTestId("crafting-badges")).toHaveTextContent("top: Wooden Chair")
    expect(screen.getByTestId("climate-badges")).toHaveTextContent("warming")
    expect(screen.getByTestId("climate-badges")).toHaveTextContent("620 ppm CO₂")
    expect(screen.getByTestId("ecoregion-badges")).toHaveTextContent("Grassland")
    expect(screen.getByTestId("ecoregion-badges")).toHaveTextContent("≈ Serengeti")
  })

  it("renders the full directory even when the snapshot fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")))

    renderHome()

    await waitFor(() => {
      expect(screen.getByTestId("dir-jobs")).toBeInTheDocument()
    })
    expect(screen.getByTestId("dir-server")).toBeInTheDocument()
    expect(screen.queryByTestId("server-badges")).not.toBeInTheDocument()
  })
})
