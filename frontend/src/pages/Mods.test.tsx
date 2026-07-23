import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { MemoryRouter } from "react-router-dom"
import Mods from "./Mods"

afterEach(cleanup)

describe("Mods reference", () => {
  it("documents all production mods with their package and site contracts", () => {
    render(
      <MemoryRouter initialEntries={["/mods"]}>
        <Mods />
      </MemoryRouter>,
    )

    const jobs = screen.getByTestId("mod-eco-jobs-tracker")
    expect(jobs).toHaveTextContent("GET /api/v1/skills")
    expect(jobs).toHaveTextContent("SPA: /jobs and /crafting")

    const replay = screen.getByTestId("mod-eco-replay")
    expect(replay).toHaveTextContent("Storage/EcoReplay.db")
    expect(replay).toHaveTextContent("/replay/api/v1/*")

    const stores = screen.getByTestId("mod-eco-store-exporter")
    expect(stores).toHaveTextContent("GET /api/v1/stores")
    expect(stores).toHaveTextContent("/preview/logistics.json")

    const telemetry = screen.getByTestId("mod-eco-telemetry")
    expect(telemetry).toHaveTextContent("GET /api/v1/climate-settings")
    expect(telemetry).toHaveTextContent("/preview/get_eco_climate.json")

    for (const mod of [jobs, replay, stores, telemetry]) {
      expect(mod).toHaveTextContent("Install-ready package")
      expect(mod).toHaveTextContent("Eco coupling and current limit")
      expect(mod).toHaveTextContent("0.13.0.4-beta-release-1024")
    }
  })

  it("links each mod to tracked source docs and the shared package contract", () => {
    render(
      <MemoryRouter initialEntries={["/mods"]}>
        <Mods />
      </MemoryRouter>,
    )

    expect(screen.getByRole("link", { name: "Jobs Tracker source and API notes ↗" })).toHaveAttribute(
      "href",
      "https://forgejo.coilysiren.me/coilyco-gaming/eco-app/src/branch/main/mods/jobs/README.md",
    )
    expect(screen.getAllByRole("link", { name: "Package contract ↗" })).toHaveLength(4)
  })
})
