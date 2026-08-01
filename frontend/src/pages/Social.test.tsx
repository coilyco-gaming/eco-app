import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import Social from "./Social"

const SURFACE = {
  fetchedAtISO: "2026-06-12T13:00:00+00:00",
  sourceBaseUrl: "http://x:3001",
  redacted: true,
  perTypeCounts: { ReputationTransfer: 2, FirstLogin: 1, Play: 3 },
  totalReputationTransfers: 2,
  totalFirstLogins: 1,
  totalPlayEvents: 3,
  playByDay: [
    [1, 2],
    [2, 1],
  ],
  firstLoginsByDay: [[1, 1]],
  newArrivals: [{ label: "player-cccc3333", day: 1 }],
  reputationEdges: [
    { source: "player-aaaa1111", target: "player-bbbb2222", amount: 5, count: 1 },
    { source: "player-bbbb2222", target: "player-aaaa1111", amount: 2, count: 1 },
  ],
  topReputationGivers: [
    ["player-aaaa1111", 5],
    ["player-bbbb2222", 2],
  ],
  topReputationReceivers: [
    ["player-aaaa1111", 2],
    ["player-bbbb2222", 5],
  ],
  warnings: [],
}

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

function stubFetch(payload: unknown = SURFACE) {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(payload))))
}

function renderSocial() {
  return render(
    <MemoryRouter initialEntries={["/social"]}>
      <Social />
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("Community activity", () => {
  it("renders activity totals and the redaction note without chat", async () => {
    stubFetch()
    renderSocial()

    await waitFor(() => {
      expect(screen.getByTestId("social-pill")).toHaveTextContent("3 play events")
    })
    expect(screen.getByTestId("social-pill")).toHaveTextContent("2 rep transfers")
    expect(screen.getByTestId("social-pill")).toHaveTextContent("1 new arrivals")
    expect(screen.getByTestId("redaction-note")).toBeInTheDocument()
    expect(screen.queryByText(/chat volume/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/recent chat/i)).not.toBeInTheDocument()
  })

  it("draws the reputation graph and arrivals chart", async () => {
    stubFetch()
    renderSocial()

    await waitFor(() => {
      expect(screen.getByTestId("rep-graph")).toBeInTheDocument()
    })
    expect(screen.getAllByTestId("rep-node")).toHaveLength(2)
    expect(screen.getAllByTestId("rep-edge")).toHaveLength(2)
    expect(screen.getByTestId("arrivals-chart")).toBeInTheDocument()
  })

  it("shows an empty state when no community activity exists", async () => {
    stubFetch({
      ...SURFACE,
      totalReputationTransfers: 0,
      totalFirstLogins: 0,
      totalPlayEvents: 0,
      reputationEdges: [],
      firstLoginsByDay: [],
    })
    renderSocial()

    await waitFor(() => {
      expect(screen.getByTestId("social-empty")).toBeInTheDocument()
    })
  })

  it("degrades when the fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")))
    renderSocial()

    await waitFor(() => {
      expect(screen.getByTestId("social-error")).toBeInTheDocument()
    })
  })
})
