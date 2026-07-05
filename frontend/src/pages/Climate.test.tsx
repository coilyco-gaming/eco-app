import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import Climate from "./Climate"

const SNAPSHOT = {
  server: { description: "Eco via Sirens", category: "Established", sourceUrl: "http://x/info" },
  days_elapsed: 59,
  admin_ok: true,
  status: "warming",
  narrative: "Climate is warming — CO2 at 325 ppm, sea level +3.05%.",
  co2: { current: 325, change_pct: 0, dataset_name: "TotalCO2", series: [] },
  sea_level: { current: 61.83, change_pct: 3.05, rate_per_day: 0.03, dataset_name: "SeaLevel", series: [] },
  pollution: { current: 437.5, source: "TotalGroundPollution", dataset_name: "TotalGroundPollution", layer_summary: null, series: [] },
  temperature: { current: 14.86, risen: 0.86, rate_per_day: 0.01, dataset_name: "AverageGlobalTemperature", series: [] },
  breakdown: {
    has_data: true,
    pollution: { lifetime: 12687, per_day: 4.2 },
    animals: { lifetime: 1450, per_day: 0.5 },
    plants: { lifetime: -28989, per_day: -357.7 },
    net_per_day: -353.0,
  },
  effects: {
    co2_now: 325,
    co2_peak: 520,
    min_floor_ppm: 325,
    at_floor: true,
    source: "default",
    temperature: { threshold_ppm: 400, ppm_per_degree: 25, headroom_ppm: 75, current_c: 14.86, risen_c: 0.86, peak_drives_c: 4.8 },
    sea_level: { threshold_ppm: 400, ppm_per_meter: 25, headroom_ppm: 75, current_m: 61.83, risen_m: 1.83, peak_drives_m: 4.8 },
  },
  explainer: [
    "CO2 sits at 325 ppm — pinned to the simulation floor (325 ppm), the cleanest the atmosphere can get.",
    "Plants are winning: they've pulled 28,989 ppm out of the air over the cycle versus 12,687 ppm added by machines, so CO2 is falling about 353.0 ppm per day.",
  ],
  earth_match: null,
  fetched_at_iso: "2026-06-15T14:00:00+00:00",
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("Climate", () => {
  it("renders the narrative, explainer, and source/sink breakdown", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(SNAPSHOT), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    )

    render(
      <MemoryRouter initialEntries={["/climate"]}>
        <Climate />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId("climate-pill")).toHaveTextContent("Climate is warming")
    })
    // Verbose explainer — the headline ask.
    expect(screen.getByTestId("explainer")).toHaveTextContent("pinned to the simulation floor")
    expect(screen.getByTestId("explainer")).toHaveTextContent("Plants are winning")
    // Atmosphere KPIs + source breakdown.
    expect(screen.getByText("325 ppm")).toBeInTheDocument()
    expect(screen.getByText("14.9 °C")).toBeInTheDocument()
    expect(screen.getByText("From pollution")).toBeInTheDocument()
    expect(screen.getByText("From plants")).toBeInTheDocument()
    expect(screen.getByTestId("climate-effects-explainer")).toHaveTextContent("pinned to the simulation floor")
    // Default ruleset → the "these are Eco defaults, retunable" disclaimer.
    expect(screen.getByTestId("climate-ruleset-source")).toHaveTextContent(
      "Eco's default climate ruleset",
    )
  })

  it("drops the defaults disclaimer when the ruleset is live", async () => {
    const live = { ...SNAPSHOT, effects: { ...SNAPSHOT.effects, source: "live" } }
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(live), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    )

    render(
      <MemoryRouter initialEntries={["/climate"]}>
        <Climate />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId("climate-ruleset-source")).toBeInTheDocument()
    })
    const src = screen.getByTestId("climate-ruleset-source")
    expect(src).toHaveTextContent("Live from this server's climate config")
    expect(src).not.toHaveTextContent("Eco's default climate ruleset")
  })

  it("degrades when the snapshot fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")))

    render(
      <MemoryRouter initialEntries={["/climate"]}>
        <Climate />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId("climate-error")).toBeInTheDocument()
    })
  })
})
