import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import World from "./World"

const WORLD = {
  view: "world",
  fetchedAtISO: "2026-06-12T13:00:00+00:00",
  sourceBaseUrl: "http://x:3001",
  totalEvents: 421,
  perActionCounts: { ConstructOrDeconstruct: 300, PolluteAir: 21, DigOrMine: 100 },
  categories: [
    { key: "construction", label: "Construction", events: 300, volume: 5400 },
    { key: "pollution", label: "Pollution", events: 21, volume: 21 },
    { key: "extraction", label: "Extraction", events: 100, volume: 2600 },
  ],
  categoryKeys: ["construction", "pollution", "extraction"],
  timeline: [
    { day: 0, counts: { construction: 120, extraction: 40 } },
    { day: 1, counts: { construction: 180, pollution: 21, extraction: 60 } },
  ],
  byCitizen: [
    ["coilysiren", 210],
    ["Citizen #129569", 90],
  ],
  byPolluter: [["coilysiren", 21]],
  byObject: [
    ["StoneItem", 3400],
    ["IronOreItem", 2600],
  ],
  hotspots: [
    { x: 384, z: 448, events: 160 },
    { x: 512, z: 0, events: 52 },
  ],
  warnings: ["TampRoad: HTTP 401"],
}

function stubWorldFetch(payload: unknown = WORLD) {
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

function renderWorld() {
  return render(
    <MemoryRouter initialEntries={["/world"]}>
      <World />
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("World", () => {
  it("renders totals, the timeline, category stats, and cross-links", async () => {
    stubWorldFetch()
    renderWorld()

    await waitFor(() => {
      expect(screen.getByTestId("world-pill")).toHaveTextContent("421 world-mutation events")
    })
    expect(screen.getByTestId("world-pill")).toHaveTextContent("300 construction")
    expect(screen.getByTestId("mutation-timeline")).toBeInTheDocument()
    expect(screen.getByTestId("timeline-legend")).toHaveTextContent("Construction")
    // Category stat tile shows the volume detail.
    expect(screen.getByText("5,400 volume")).toBeInTheDocument()
    expect(screen.getByTestId("link-climate")).toHaveAttribute("href", "/climate")
    expect(screen.getByTestId("link-crafting")).toHaveAttribute("href", "/crafting")
  })

  it("ranks world-shapers, polluters, prettified objects, and hotspots", async () => {
    stubWorldFetch()
    renderWorld()

    await waitFor(() => {
      expect(screen.getByTestId("shapers")).toBeInTheDocument()
    })
    expect(screen.getAllByTestId("shapers-row")).toHaveLength(2)
    // Polluter board is populated from the pollution-category split.
    expect(screen.getByTestId("polluters")).toHaveTextContent("coilysiren")
    // Object ids are prettified (StoneItem -> Stone), citizen names shown
    // verbatim. coilysiren tops both the shaper and polluter boards.
    expect(screen.getByText("Stone")).toBeInTheDocument()
    expect(screen.getAllByText("coilysiren").length).toBeGreaterThan(0)
    expect(screen.getByText("(384, 448)")).toBeInTheDocument()
    // Non-fatal fetch warnings surface.
    expect(screen.getByTestId("world-warnings")).toHaveTextContent("TampRoad: HTTP 401")
  })

  it("shows an empty state when no events are recorded", async () => {
    stubWorldFetch({ ...WORLD, totalEvents: 0, categories: [], timeline: [] })
    renderWorld()

    await waitFor(() => {
      expect(screen.getByTestId("world-empty")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("mutation-timeline")).not.toBeInTheDocument()
  })

  it("degrades when the world fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")))
    renderWorld()

    await waitFor(() => {
      expect(screen.getByTestId("world-error")).toBeInTheDocument()
    })
  })
})
