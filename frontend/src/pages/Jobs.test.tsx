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

  it("shows the degraded note when the API is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")))
    renderJobs()

    await waitFor(() => {
      expect(screen.getByTestId("jobs-error")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("mock-banner")).not.toBeInTheDocument()
  })
})
