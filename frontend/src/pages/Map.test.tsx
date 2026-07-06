import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { EcoregionSnapshot } from "../lib/ecoregionApi"
import type { MapPayload } from "../lib/mapApi"
import MapPage from "./Map"

const SNAP: EcoregionSnapshot = {
  view: "eco_ecoregion",
  sourceUrl: "http://eco.example.com:3001/info",
  biomes: [
    { name: "OceanBiome", display: "Ocean", percent: 13, sharePercent: 33, color: "#4a9cb8" },
    { name: "GrasslandBiome", display: "Grassland", percent: 7, sharePercent: 18, color: "#a5d14a" },
    { name: "CoastalWater", display: "Coastal & shallow sea", percent: 36, sharePercent: 0, color: "#5fb0cf", isWater: true },
    { name: "FreshWater", display: "Fresh water", percent: 5, sharePercent: 0, color: "#7fc8bf", isWater: true },
  ],
  unclassifiedPercent: 39,
  rawSumPercent: 20,
  classifiedPercent: 61,
  ecoregionMatches: [
    { name: "Indo-Pacific archipelago", description: "islands and warm seas", similarity: 0.83 },
  ],
  drift: {
    boom: [{ name: "Deer", first: 100, latest: 200, deltaRel: 1.0, fromZero: false }],
    bust: [{ name: "Wolf", first: 50, latest: 25, deltaRel: -0.5, fromZero: false }],
    speciesSeen: 2,
    speciesWithDrift: 2,
  },
  adminAvailable: true,
}

const WORLD = {
  view: "world",
  fetchedAtISO: "2026-06-12T13:00:00+00:00",
  sourceBaseUrl: "http://x:3001",
  totalEvents: 421,
  perActionCounts: { ConstructOrDeconstruct: 300 },
  categories: [{ key: "construction", label: "Construction", events: 300, volume: 5400 }],
  categoryKeys: ["construction"],
  timeline: [{ day: 0, counts: { construction: 300 } }],
  byCitizen: [["coilysiren", 210]],
  byPolluter: [["coilysiren", 21]],
  // Touch counts (#82) — small integers, not runaway summed Count.
  byObject: [
    ["DirtRampItem", 42],
    ["StoneItem", 30],
  ],
  hotspots: [
    { x: 384, z: 448, events: 160 },
    { x: 512, z: 0, events: 52 },
  ],
  warnings: [],
}

const _TINY = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=="

const MAP: MapPayload = {
  view: "eco_map",
  sourceUrl: "http://eco.example.com:3001",
  worldDim: { x: 1000, y: 200, z: 1000 },
  renderSize: 512,
  gifDataUri: _TINY,
  pollutionDataUri: null,
  biomeLayers: [{ name: "OceanBiome", display: "Ocean", color: "#4a9cb8", dataUri: _TINY }],
  polygons: [
    { owner: "alice", deed: "Alice's Homestead", fill: "hsla(1,50%,50%,0.4)", stroke: "hsla(1,60%,35%,0.9)", points: "10,10 20,10 20,20 10,20" },
  ],
  deedCount: 1,
  ownerCount: 1,
  owners: ["alice"],
  owner_colors: { alice: "hsla(1,50%,50%,0.4)" },
  owner_strokes: { alice: "hsla(1,60%,35%,0.9)" },
}

function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      let body: unknown = {}
      if (url.includes("get_eco_ecoregion")) body = SNAP
      else if (url.includes("world.json")) body = WORLD
      else if (url.includes("preview-map.json")) body = MAP
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
    }),
  )
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/map"]}>
      <MapPage />
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("Map page", () => {
  it("shows a loading state before data resolves", () => {
    stubFetch()
    renderPage()
    expect(screen.getByTestId("loading")).toBeInTheDocument()
  })

  it("renders the map frame with deed polygons and hotspot overlay", async () => {
    stubFetch()
    renderPage()
    await waitFor(() => expect(screen.getByTestId("map-frame")).toBeInTheDocument())
    // Two activity hotspots overlaid on the actual map.
    expect(screen.getAllByTestId("map-hotspot")).toHaveLength(2)
    // The deed polygon is drawn.
    expect(screen.getByTestId("map-overlay").querySelector("polygon")).toBeTruthy()
    expect(screen.getByTestId("map-owners")).toHaveTextContent("alice")
  })

  it("reclassifies water so unclassified is far below the old 61%", async () => {
    stubFetch()
    renderPage()
    await waitFor(() => expect(screen.getByTestId("eco-legend")).toBeInTheDocument())
    const legend = screen.getByTestId("eco-legend")
    expect(legend).toHaveTextContent("Coastal & shallow sea")
    expect(legend).toHaveTextContent("Fresh water")
    // 39% unclassified, not 61%.
    expect(legend).toHaveTextContent("39%")
  })

  it("highlights a biome raster on the map when its legend row is hovered", async () => {
    stubFetch()
    renderPage()
    await waitFor(() => expect(screen.getByTestId("map-biome-OceanBiome")).toBeInTheDocument())
    const raster = screen.getByTestId("map-biome-OceanBiome")
    expect(raster).toHaveStyle({ opacity: "0" })
    fireEvent.mouseEnter(screen.getByTestId("biome-legend-OceanBiome"))
    expect(raster).toHaveStyle({ opacity: "0.92" })
    fireEvent.mouseLeave(screen.getByTestId("biome-legend-OceanBiome"))
    expect(raster).toHaveStyle({ opacity: "0" })
  })

  it("shows most-touched objects as small touch counts, not runaway sums", async () => {
    stubFetch()
    renderPage()
    await waitFor(() => expect(screen.getByTestId("objects")).toBeInTheDocument())
    const objects = screen.getByTestId("objects")
    expect(objects).toHaveTextContent("Dirt Ramp")
    expect(objects).toHaveTextContent("42")
    expect(objects).not.toHaveTextContent("19,516,641")
  })

  it("carries over the ecoregion matches and world timeline into one page", async () => {
    stubFetch()
    renderPage()
    await waitFor(() => expect(screen.getByTestId("eco-matches")).toBeInTheDocument())
    expect(screen.getByTestId("eco-matches")).toHaveTextContent("Indo-Pacific archipelago")
    expect(screen.getByTestId("mutation-timeline")).toBeInTheDocument()
    expect(screen.getByTestId("shapers")).toHaveTextContent("coilysiren")
  })
})
