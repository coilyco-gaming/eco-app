import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import Civics from "./Civics"

const REPORT = {
  fetchedAtISO: "2026-06-12T13:00:00+00:00",
  sourceBaseUrl: "http://x:3001",
  totalEvents: 12,
  perActionCounts: { Vote: 3, DidntVote: 1 },
  electionsStarted: 1,
  electionsWon: 1,
  electionsLost: 0,
  votesCast: 3,
  abstentions: 1,
  turnoutRate: 0.75,
  recentElections: [{ subject: "MayorRace", proposer: "alice", day: 3 }],
  recentOutcomes: [{ subject: "MayorRace", winner: "alice", day: 3 }],
  topVoters: [
    ["alice", 2],
    ["bob", 1],
  ],
  citizensGained: 2,
  citizensLost: 1,
  netCitizens: 1,
  residencyMoves: 1,
  demographicChanges: 0,
  recentDemographics: [
    { name: "bob", day: 2, kind: "joined", settlement: "Rivertown" },
    { name: "Citizen #104", day: 2, kind: "left", settlement: "Rivertown" },
  ],
  settlementsFounded: 1,
  homesteadsStarted: 1,
  recentSettlements: [
    { subject: "Rivertown", founder: "alice", day: 2, kind: "settlement" },
    { subject: "BobsFarm", founder: "bob", day: 2, kind: "homestead" },
  ],
  trend: {
    Vote: [
      [0, 0],
      [1, 1],
      [2, 3],
    ],
    DidntVote: [
      [1, 0],
      [2, 1],
    ],
  },
  warnings: [],
}

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

function stubFetch(payload: unknown = REPORT) {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(payload))))
}

function renderCivics(entry = "/civics") {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Civics />
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("Civics", () => {
  it("renders the civic snapshot, turnout, and both cross-links", async () => {
    stubFetch()
    renderCivics()

    await waitFor(() => {
      expect(screen.getByTestId("civics-pill")).toHaveTextContent("12 civic events")
    })
    expect(screen.getByTestId("civics-pill")).toHaveTextContent("75% turnout")
    expect(screen.getByTestId("civics-stats")).toHaveTextContent("Turnout")
    expect(screen.getByTestId("link-info")).toHaveAttribute("href", "/info")
  })

  it("charts turnout over time with a two-series legend", async () => {
    stubFetch()
    renderCivics()

    await waitFor(() => {
      expect(screen.getByTestId("turnout-chart")).toBeInTheDocument()
    })
    expect(screen.getByTestId("turnout-legend")).toHaveTextContent("votes cast")
    expect(screen.getByTestId("turnout-legend")).toHaveTextContent("abstentions")
  })

  it("lists recent elections with proposer names", async () => {
    stubFetch()
    renderCivics()

    await waitFor(() => {
      expect(screen.getByTestId("elections-table")).toBeInTheDocument()
    })
    expect(screen.getByTestId("election-row")).toHaveTextContent("MayorRace")
    expect(screen.getByTestId("election-row")).toHaveTextContent("alice")
  })

  it("ranks most-active voters and shows settlements", async () => {
    stubFetch()
    renderCivics()

    await waitFor(() => {
      expect(screen.getAllByTestId("voter-row").length).toBeGreaterThan(0)
    })
    // alice voted the most.
    expect(screen.getAllByText("alice").length).toBeGreaterThan(0)
    expect(screen.getByTestId("settlements-list")).toHaveTextContent("Rivertown")
  })

  it("shows demographic arrivals and departures with the id fallback", async () => {
    stubFetch()
    renderCivics()

    await waitFor(() => {
      expect(screen.getByTestId("demographics-table")).toBeInTheDocument()
    })
    expect(screen.getAllByTestId("demographic-row")).toHaveLength(2)
    // Unmapped id keeps its "Citizen #<id>" label verbatim.
    expect(screen.getByText("Citizen #104")).toBeInTheDocument()
  })

  it("shows an empty state when no civic events are recorded", async () => {
    stubFetch({
      ...REPORT,
      totalEvents: 0,
      recentElections: [],
      recentSettlements: [],
      recentDemographics: [],
      topVoters: [],
      trend: {},
    })
    renderCivics()

    await waitFor(() => {
      expect(screen.getByTestId("civics-empty")).toBeInTheDocument()
    })
  })

  it("degrades when the report fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")))
    renderCivics()

    await waitFor(() => {
      expect(screen.getByTestId("civics-error")).toBeInTheDocument()
    })
  })
})
