import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import Landing from "./Landing"
import type { EcoStatus } from "../lib/api"

const SAMPLE: EcoStatus = {
  view: "eco_status",
  fetchedAtISO: "2026-06-12T11:46:33+00:00",
  sourceUrl: "http://example.test:3001/info",
  server: {
    description: "<color=green>Eco</color> via <color=blue>Sirens</color> | Cycle 13",
    detailedDescription: "Cycle 13.",
    category: "Established",
    discord: "https://discord.gg/example",
    version: "0.13.0.4 beta release-1024",
    language: "English",
    paused: false,
    hasPassword: false,
    adminOnline: false,
  },
  players: { online: 1, total: 114, activeAndOnline: 4, peakActive: 38 },
  world: { size: "0.52km²", plants: 64342, animals: 0, laws: 10, totalCulture: 2254.76 },
  cycle: {
    daysRunning: 56,
    daysUntilMeteor: 3,
    hasMeteor: true,
    collaboration: "HighCollaboration",
    gameSpeed: "Slow",
    simulationLevel: "Normal",
  },
  economy: { description: "1341 trades, 0 contracts" },
  achievements: [],
}

function renderLanding() {
  return render(
    <MemoryRouter>
      <Landing />
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

describe("Landing", () => {
  it("renders the live snapshot from /preview.json", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(SAMPLE), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    )

    renderLanding()

    await waitFor(() => {
      expect(screen.getByTestId("meteor-count")).toHaveTextContent("3 days until the meteor")
    })
    expect(screen.getByTestId("live-pill")).toHaveTextContent("1 online now")
    expect(screen.getByText("Eco via Sirens | Cycle 13")).toBeInTheDocument()
    expect(screen.getByText("64,342")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Join the Discord" })).toHaveAttribute(
      "href",
      "https://discord.gg/example",
    )
  })

  it("keeps the shell useful when the snapshot fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")))

    renderLanding()

    await waitFor(() => {
      expect(screen.getByTestId("live-pill")).toHaveTextContent("live snapshot unavailable")
    })
    expect(screen.getByRole("link", { name: "Eco on Steam" })).toBeInTheDocument()
    expect(screen.queryByTestId("meteor-count")).not.toBeInTheDocument()
  })
})
