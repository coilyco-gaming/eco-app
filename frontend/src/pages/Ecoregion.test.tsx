import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { EcoregionSnapshot } from "../lib/ecoregionApi"
import Ecoregion from "./Ecoregion"

const SNAP: EcoregionSnapshot = {
  view: "eco_ecoregion",
  sourceUrl: "http://eco.example.com:3001/info",
  biomes: [
    { name: "OceanBiome", display: "Ocean", percent: 13, sharePercent: 33, color: "#4a9cb8" },
    { name: "GrasslandBiome", display: "Grassland", percent: 7, sharePercent: 18, color: "#a5d14a" },
    { name: "ForestBiome", display: "Forest", percent: 0, sharePercent: 0, color: "#5a8a3a" },
  ],
  unclassifiedPercent: 80,
  rawSumPercent: 20,
  classifiedPercent: 20,
  ecoregionMatches: [
    { name: "Indo-Pacific archipelago", description: "islands and warm seas", similarity: 0.83 },
    { name: "Great Plains temperate grassland", description: "continental prairie", similarity: 0.41 },
  ],
  drift: {
    boom: [
      { name: "Deer", first: 100, latest: 200, deltaRel: 1.0, fromZero: false },
      { name: "Rabbit", first: 0, latest: 40, deltaRel: null, fromZero: true },
    ],
    bust: [{ name: "Wolf", first: 50, latest: 25, deltaRel: -0.5, fromZero: false }],
    speciesSeen: 3,
    speciesWithDrift: 3,
  },
  adminAvailable: true,
}

function stubFetch(snap: EcoregionSnapshot) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(snap), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  )
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/ecoregion"]}>
      <Ecoregion />
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("Ecoregion", () => {
  it("renders the donut legend with raw percents and an unclassified slice", async () => {
    stubFetch(SNAP)
    renderPage()

    await waitFor(() => {
      expect(screen.getByTestId("eco-legend")).toBeInTheDocument()
    })
    const legend = screen.getByTestId("eco-legend")
    // Only biomes with a nonzero raw percent appear (ForestBiome is dropped).
    expect(legend).toHaveTextContent("Ocean")
    expect(legend).toHaveTextContent("13%")
    expect(legend).not.toHaveTextContent("Forest")
    // The gap to 100% is filled by an explicit unclassified slice.
    expect(legend).toHaveTextContent("Unclassified / mixed terrain")
    expect(legend).toHaveTextContent("80%")
  })

  it("lists the closest ecoregion matches with similarity scores", async () => {
    stubFetch(SNAP)
    renderPage()

    await waitFor(() => {
      expect(screen.getByTestId("eco-matches")).toBeInTheDocument()
    })
    const matches = screen.getByTestId("eco-matches")
    expect(matches).toHaveTextContent("Indo-Pacific archipelago")
    expect(matches).toHaveTextContent("0.83")
    expect(screen.getByTestId("eco-pill")).toHaveTextContent("Closest to Indo-Pacific archipelago")
  })

  it("splits drift into boom and bust, rendering a from-zero grower as 'new'", async () => {
    stubFetch(SNAP)
    renderPage()

    await waitFor(() => {
      expect(screen.getByTestId("eco-drift")).toBeInTheDocument()
    })
    expect(screen.getAllByTestId("drift-add-row")).toHaveLength(2)
    expect(screen.getAllByTestId("drift-remove-row")).toHaveLength(1)
    expect(screen.getByText("+100%")).toBeInTheDocument()
    expect(screen.getByText("new")).toBeInTheDocument()
    expect(screen.getByText("-50%")).toBeInTheDocument()
  })

  it("shows the minimal-drift placeholder when nothing has moved", async () => {
    stubFetch({
      ...SNAP,
      drift: { boom: [], bust: [], speciesSeen: 42, speciesWithDrift: 0 },
    })
    renderPage()

    await waitFor(() => {
      expect(screen.getByTestId("eco-drift-minimal")).toBeInTheDocument()
    })
    expect(screen.getByTestId("eco-drift-minimal")).toHaveTextContent("42 species")
  })

  it("shows an admin-unavailable note when the exporter is off", async () => {
    stubFetch({ ...SNAP, adminAvailable: false })
    renderPage()

    await waitFor(() => {
      expect(screen.getByTestId("eco-drift-admin")).toBeInTheDocument()
    })
  })

  it("degrades to an error pill when the fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")))
    renderPage()

    await waitFor(() => {
      expect(screen.getByTestId("eco-error")).toBeInTheDocument()
    })
  })
})
