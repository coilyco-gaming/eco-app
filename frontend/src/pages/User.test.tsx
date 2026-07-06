import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import { encodeUserHex } from "../lib/usersApi"
import User from "./User"

const DOSSIER = {
  username: "coilysiren",
  found: true,
  fetchedAtISO: "2026-06-12T13:00:00+00:00",
  available: { jobs: true, trades: true, crafting: true, world: true, currency: true },
  jobs: {
    active: true,
    lastSeenISO: "2026-05-08T12:34:56+00:00",
    specialties: [{ specialty: "Basic Carpentry", level: 5, active: true }],
  },
  trades: {
    currencySpent: 250,
    currencyEarned: 225,
    trades: [
      {
        buyer: "coilysiren",
        seller: "ekans",
        shopOwner: "ekans",
        item: "IronIngotItem",
        currency: "Credit",
        currencyAmount: 250,
        day: 3,
      },
    ],
  },
  crafting: { events: 42 },
  civics: {
    votesCast: 3,
    elections: [{ subject: "Head of State", day: 4, role: "won" }],
    demographics: [],
    settlements: [{ subject: "Town", day: 2, kind: "settlement" }],
  },
  currency: { holdings: [{ currency: "Credit", balance: 1200, account: "coily Account" }] },
  progression: {
    levelUpCount: 4,
    trajectory: {
      name: "coilysiren",
      eventCount: 9,
      characterLevel: 12,
      professions: [{ name: "Carpenter", pretty: "Carpenter" }],
      specialties: [],
      timeline: [{ day: 3, kind: "specialty", skill: "BasicCarpentry", pretty: "Basic Carpentry", level: 5 }],
    },
  },
  world: { shaperEvents: 30, pollutionEvents: 2 },
  roster: ["coilysiren", "ekans"],
  warnings: ["currency holdings list the top holders per currency"],
}

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

function renderUser(hex: string) {
  return render(
    <MemoryRouter initialEntries={[`/users/${hex}`]}>
      <Routes>
        <Route path="/users/:hex" element={<User />} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("User dossier", () => {
  it("decodes the hex username and renders every populated surface", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(DOSSIER))))
    renderUser(encodeUserHex("coilysiren"))

    await waitFor(() => {
      expect(screen.getByTestId("user-name")).toHaveTextContent("coilysiren")
    })
    // The fetch used the decoded username, not the hex.
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("name=coilysiren"),
      expect.anything(),
    )
    expect(screen.getByTestId("user-specialties")).toHaveTextContent("Basic Carpentry")
    expect(screen.getByTestId("user-trades")).toHaveTextContent("Iron Ingot")
    expect(screen.getByTestId("user-holdings")).toHaveTextContent("Credit")
    expect(screen.getByTestId("user-civics-events")).toHaveTextContent("Head of State")
    expect(screen.getByTestId("user-timeline")).toHaveTextContent("Basic Carpentry")
    expect(screen.getByTestId("user-warnings")).toHaveTextContent("top holders")
  })

  it("shows a bad-link state for a non-hex segment without fetching", async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal("fetch", fetchSpy)
    renderUser("not-hex")

    await waitFor(() => {
      expect(screen.getByTestId("user-bad-hex")).toBeInTheDocument()
    })
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it("shows a not-found note when no data mentions the user", async () => {
    const empty = { ...DOSSIER, found: false, jobs: null, trades: null, crafting: null, civics: null, currency: null, progression: null, world: null, warnings: [] }
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(empty))))
    renderUser(encodeUserHex("ghost"))

    await waitFor(() => {
      expect(screen.getByTestId("user-not-found")).toBeInTheDocument()
    })
  })

  it("degrades when the dossier fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")))
    renderUser(encodeUserHex("coilysiren"))

    await waitFor(() => {
      expect(screen.getByTestId("user-error")).toBeInTheDocument()
    })
  })
})
