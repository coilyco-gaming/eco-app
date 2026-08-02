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

    expect(
      screen.getByText(/intelligence and companionship for serious Eco servers/i),
    ).toHaveTextContent("what happened while you were away")
    expect(screen.getByTestId("dir-info")).toHaveAttribute("href", "/info")
    expect(screen.getByTestId("dir-jobs")).toHaveAttribute("href", "/jobs")
    expect(screen.getByTestId("dir-wiki")).toHaveAttribute("href", "/wiki")
    // The eco-gnome calculator is a homepage card that links out to the gnome
    // service, not a /calculator route anymore (eco-app#90).
    expect(screen.getByTestId("dir-gnome")).toHaveAttribute(
      "href",
      "https://eco-gnome.coilysiren.me/",
    )
    // /economy is gone entirely (eco-app#90) — no economy card. The standalone
    // trades and climate cards folded into Trade and World respectively.
    expect(screen.queryByTestId("dir-economy")).not.toBeInTheDocument()
    expect(screen.queryByTestId("dir-trades")).not.toBeInTheDocument()
    expect(screen.queryByTestId("dir-climate")).not.toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByTestId("info-badges")).toHaveTextContent("3d to meteor")
    })
    expect(screen.getByTestId("info-badges")).toHaveTextContent("1 online")
    expect(screen.getByRole("link", { name: "Join the Discord" })).toHaveAttribute(
      "href",
      "https://discord.gg/example",
    )
  })

  it("renders per-surface sub-card badges from the live pulse endpoints", async () => {
    const byUrl: Record<string, unknown> = {
      "/preview.json": SAMPLE_STATUS,
      "/preview/get_trades.json": {
        totalTrades: 1341,
        totalCurrencyVolume: 4907,
        byItem: [["BunWulfRawMeatItem", 90, 400]],
      },
      "/preview/get_crafting_atlas.json": {
        totalEvents: 512,
        byCrafted: [["WoodenChairItem", 40]],
      },
      "/preview/get_climate.json": {
        status: "warming",
        co2: { current: 620 },
      },
      "/preview/get_region.json": {
        biomes: [{ display: "Grassland" }],
        ecoregionMatches: [{ name: "Serengeti" }],
      },
      "/preview/world.json": {
        totalEvents: 421,
        categories: [{ key: "construction", label: "Construction", events: 300, volume: 1 }],
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

    // Trade + trades ledger are one card now (eco-app#90): volume and the trade
    // count come from the ledger's totalCurrencyVolume / totalTrades, and
    // markets falls back to a graceful 0 when the market plane is empty.
    await waitFor(() => {
      expect(screen.getByTestId("trade-badges")).toHaveTextContent("1,341 trades")
    })
    expect(screen.getByTestId("trade-badges")).toHaveTextContent("4,907 volume")
    expect(screen.getByTestId("trade-badges")).toHaveTextContent("0 markets")
    expect(screen.getByTestId("trade-badges")).toHaveTextContent("top: Bun Wulf Raw Meat")
    expect(screen.getByTestId("crafting-badges")).toHaveTextContent("512 crafts")
    expect(screen.getByTestId("crafting-badges")).toHaveTextContent("top: Wooden Chair")
    // World + ecoregion merged into the one /map card (eco-app#82) and climate
    // folded in (eco-app#90): its badge strip carries world events, the busiest
    // category, the dominant biome, and the climate headline + CO₂.
    expect(screen.getByTestId("world-badges")).toHaveTextContent("421 events")
    expect(screen.getByTestId("world-badges")).toHaveTextContent("Construction")
    expect(screen.getByTestId("world-badges")).toHaveTextContent("Grassland")
    expect(screen.getByTestId("world-badges")).toHaveTextContent("warming")
    expect(screen.getByTestId("world-badges")).toHaveTextContent("620 ppm CO₂")
  })

  it("renders the full directory even when the snapshot fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")))

    renderHome()

    await waitFor(() => {
      expect(screen.getByTestId("dir-jobs")).toBeInTheDocument()
    })
    expect(screen.getByTestId("dir-info")).toBeInTheDocument()
    expect(screen.queryByTestId("info-badges")).not.toBeInTheDocument()
  })
})
