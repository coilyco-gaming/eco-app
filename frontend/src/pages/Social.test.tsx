import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import Social from "./Social"

const SURFACE = {
  fetchedAtISO: "2026-06-12T13:00:00+00:00",
  sourceBaseUrl: "http://x:3001",
  redacted: true,
  latestTimeS: 300000,
  perTypeCounts: { ChatSent: 4, ReputationTransfer: 2, FirstLogin: 1, Play: 3 },
  totalChat: 4,
  totalReputationTransfers: 2,
  totalFirstLogins: 1,
  totalPlayEvents: 3,
  chatByDay: [
    [1, 1],
    [2, 3],
  ],
  playByDay: [
    [1, 2],
    [2, 1],
  ],
  firstLoginsByDay: [[1, 1]],
  chatByChannel: [
    ["General", 3],
    ["Trade", 1],
  ],
  topChatters: [
    ["player-aaaa1111", 3],
    ["player-bbbb2222", 1],
  ],
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
  recentChat: [
    { day: 2, timeS: 290000, author: "player-aaaa1111", channel: "General", message: "selling iron, ping player-bbbb2222" },
    { day: 1, timeS: 100000, author: "player-bbbb2222", channel: "Trade", message: "anyone need wood" },
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

function renderSocial(entry = "/social") {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Social />
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("Social", () => {
  it("renders totals, the redaction note, and the chat feed", async () => {
    stubFetch()
    renderSocial()

    await waitFor(() => {
      expect(screen.getByTestId("social-pill")).toHaveTextContent("4 messages")
    })
    expect(screen.getByTestId("social-pill")).toHaveTextContent("2 rep transfers")
    expect(screen.getByTestId("social-pill")).toHaveTextContent("1 new arrivals")
    // Redaction posture is surfaced to the user.
    expect(screen.getByTestId("redaction-note")).toBeInTheDocument()
    // One row per redacted chat sample; author shows the handle, not a real name.
    expect(screen.getAllByTestId("chat-row")).toHaveLength(2)
    expect(screen.getAllByText("player-aaaa1111").length).toBeGreaterThan(0)
  })

  it("charts chat volume and draws the reputation graph", async () => {
    stubFetch()
    renderSocial()

    await waitFor(() => {
      expect(screen.getByTestId("chat-volume-chart")).toBeInTheDocument()
    })
    expect(screen.getByTestId("rep-graph")).toBeInTheDocument()
    // Two nodes, two directed edges.
    expect(screen.getAllByTestId("rep-node")).toHaveLength(2)
    expect(screen.getAllByTestId("rep-edge")).toHaveLength(2)
    // New-arrivals chart renders when there is login history.
    expect(screen.getByTestId("arrivals-chart")).toBeInTheDocument()
  })

  it("never surfaces a raw player name on the redacted feed", async () => {
    stubFetch()
    renderSocial()

    await waitFor(() => {
      expect(screen.getByTestId("chat-feed")).toBeInTheDocument()
    })
    // The message body carries only a handle, never a plaintext name.
    expect(screen.getByTestId("chat-feed")).toHaveTextContent(
      "selling iron, ping player-bbbb2222",
    )
  })

  it("shows an empty state when nothing has happened yet", async () => {
    stubFetch({
      ...SURFACE,
      totalChat: 0,
      totalReputationTransfers: 0,
      totalFirstLogins: 0,
      totalPlayEvents: 0,
      chatByDay: [],
      reputationEdges: [],
      recentChat: [],
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
