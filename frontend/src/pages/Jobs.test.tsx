import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import Jobs from "./Jobs"

const META = { mockData: true }
const PROFESSIONS = [
  { profession: "Carpentry", active: 2, total: 3, players: ["coilysiren", "ekans"] },
  { profession: "Masonry", active: 0, total: 0, players: [] },
]
const SPECIALTIES = [
  {
    specialty: "Basic Carpentry",
    profession: "Carpentry",
    active: 1,
    total: 2,
    holders: [
      { player: "coilysiren", level: 5, active: true },
      { player: "ekans", level: 2, active: false },
    ],
  },
]
const PLAYERS = [
  {
    name: "coilysiren",
    active: true,
    specialties: [{ specialty: "Basic Carpentry", level: 5, active: true }],
  },
  { name: "ekans", active: false, specialties: [] },
]
const PROGRESSION = {
  fetchedAtISO: "2026-06-12T13:00:00+00:00",
  sourceBaseUrl: "http://x:3001",
  totalEvents: 3,
  perActionCounts: { GainSpecialty: 2, SpecialtyLevelUp: 1 },
  citizens: [
    {
      name: "coilysiren",
      eventCount: 3,
      firstDay: 1,
      lastDay: 3,
      characterLevel: 4,
      levelUpCount: 1,
      professions: [{ name: "Carpenter", pretty: "Carpenter" }],
      specialties: [{ name: "BasicCarpentry", pretty: "Basic Carpentry", level: 5 }],
      timeline: [
        { day: 3, time: 300000, kind: "specialty_levelup", skill: "BasicCarpentry", pretty: "Basic Carpentry", level: 5 },
        { day: 1, time: 100000, kind: "specialty", skill: "BasicCarpentry", pretty: "Basic Carpentry", level: 1 },
      ],
    },
  ],
  trends: { specialty: [[1, 2]] },
  bySpecialty: [["BasicCarpentry", 2]],
  byProfession: [["Carpenter", 1]],
  classCompletions: [],
  topLevelers: [["coilysiren", 1]],
  dailySeries: {},
  warnings: [],
}

function stubJobsFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      const body = url.endsWith("/meta")
        ? META
        : url.endsWith("/professions")
          ? PROFESSIONS
          : url.endsWith("/specialties")
            ? SPECIALTIES
            : url.endsWith("/players")
              ? PLAYERS
              : url.endsWith("/preview/progression.json")
                ? PROGRESSION
                : null
      if (body === null) return Promise.reject(new Error(`unexpected fetch: ${url}`))
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
    }),
  )
}

function renderJobs() {
  return render(
    <MemoryRouter initialEntries={["/jobs"]}>
      <Jobs />
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("Jobs", () => {
  it("renders all three sections from the jobs API", async () => {
    stubJobsFetch()
    renderJobs()

    await waitFor(() => {
      expect(screen.getByText("Professions")).toBeInTheDocument()
    })
    expect(screen.getByRole("button", { name: /Carpentry/ })).toBeInTheDocument()
    expect(screen.getAllByText("Basic Carpentry").length).toBeGreaterThan(0)
    expect(screen.getAllByText("ekans").length).toBeGreaterThan(0)
    expect(screen.getByTestId("mock-banner")).toBeInTheDocument()
  })

  it("expands a profession to list its players", async () => {
    stubJobsFetch()
    renderJobs()

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Carpentry/ })).toBeInTheDocument()
    })
    // coilysiren appears once before expanding (the Players section card);
    // expanding Carpentry adds the profession's member row.
    const before = screen.getAllByText("coilysiren").length

    fireEvent.click(screen.getByRole("button", { name: /Carpentry/ }))
    expect(screen.getAllByText("coilysiren").length).toBe(before + 1)
  })

  it("folds the server-wide progression layer and leaderboards into the page", async () => {
    stubJobsFetch()
    renderJobs()

    await waitFor(() => {
      expect(screen.getByTestId("jobs-progression")).toBeInTheDocument()
    })
    // The merged trajectory layer carries the server-wide trends + leaderboards
    // that used to live on the standalone /progression page.
    expect(screen.getByText("How the world got here")).toBeInTheDocument()
    expect(screen.getByTestId("trend-grid")).toBeInTheDocument()
    expect(screen.getByText("Most-gained specialties")).toBeInTheDocument()
    expect(screen.getByText("Busiest levelers")).toBeInTheDocument()
    expect(screen.getAllByTestId("rank-row").length).toBeGreaterThan(0)
    // There is no standalone progression page to link out to anymore.
    expect(screen.queryByRole("link", { name: /progression history/i })).not.toBeInTheDocument()
  })

  it("renders the per-player skill timeline from progression", async () => {
    stubJobsFetch()
    renderJobs()

    await waitFor(() => {
      expect(screen.getByTestId("jobs-progression")).toBeInTheDocument()
    })
    // coilysiren has a trajectory → the per-player history toggle appears; ekans
    // has none, so exactly one toggle renders.
    const toggles = screen.getAllByTestId("player-history-toggle")
    expect(toggles).toHaveLength(1)
    fireEvent.click(toggles[0])
    expect(screen.getByTestId("player-history")).toBeInTheDocument()
    expect(screen.getByText(/specialty level-ups: Basic Carpentry/)).toBeInTheDocument()
  })

  it("hides the progression layer when progression is unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input)
        const body = url.endsWith("/meta")
          ? META
          : url.endsWith("/professions")
            ? PROFESSIONS
            : url.endsWith("/specialties")
              ? SPECIALTIES
              : url.endsWith("/players")
                ? PLAYERS
                : null
        // Progression fetch fails → the jobs page renders exactly as before.
        if (body === null) return Promise.reject(new Error(`no progression: ${url}`))
        return Promise.resolve(
          new Response(JSON.stringify(body), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        )
      }),
    )
    renderJobs()

    await waitFor(() => {
      expect(screen.getByText("Professions")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("jobs-progression")).not.toBeInTheDocument()
    expect(screen.queryByTestId("player-history-toggle")).not.toBeInTheDocument()
  })

  it("shows the degraded note when the API is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")))
    renderJobs()

    await waitFor(() => {
      expect(screen.getByTestId("jobs-error")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("mock-banner")).not.toBeInTheDocument()
  })
})
