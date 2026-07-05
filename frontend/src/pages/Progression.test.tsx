import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import Progression from "./Progression"

const HISTORY = {
  fetchedAtISO: "2026-06-12T13:00:00+00:00",
  sourceBaseUrl: "http://x:3001",
  totalEvents: 9,
  perActionCounts: { GainSpecialty: 3, SpecialtyLevelUp: 3, CharacterLevelUp: 2, CompleteClass: 1 },
  citizens: [
    {
      name: "coilysiren",
      eventCount: 6,
      firstDay: 1,
      lastDay: 4,
      characterLevel: 3,
      levelUpCount: 4,
      professions: [{ name: "Engineer", pretty: "Engineer" }],
      specialties: [{ name: "BlacksmithSkill", pretty: "Blacksmith Skill", level: 3 }],
      timeline: [
        { day: 4, time: 400000, kind: "character_levelup", skill: "", pretty: "", level: 3 },
        { day: 1, time: 100000, kind: "specialty", skill: "BlacksmithSkill", pretty: "Blacksmith Skill", level: 1 },
      ],
    },
    {
      name: "Citizen #130409",
      eventCount: 3,
      firstDay: 1,
      lastDay: 2,
      characterLevel: null,
      levelUpCount: 1,
      professions: [],
      specialties: [{ name: "FarmingSkill", pretty: "Farming Skill", level: 2 }],
      timeline: [
        { day: 2, time: 160000, kind: "specialty_levelup", skill: "FarmingSkill", pretty: "Farming Skill", level: 2 },
      ],
    },
  ],
  trends: {
    specialty: [
      [1, 2],
      [2, 1],
    ],
    character_levelup: [[4, 2]],
  },
  bySpecialty: [
    ["BlacksmithSkill", 2],
    ["FarmingSkill", 1],
  ],
  byProfession: [["Engineer", 1]],
  classCompletions: [["SmithingClass", 1]],
  topLevelers: [
    ["coilysiren", 4],
    ["Citizen #130409", 1],
  ],
  dailySeries: {},
  warnings: ["EnrollAction: HTTP 401"],
}

function stubFetch(payload: unknown = HISTORY) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  )
}

function renderProgression(entry = "/progression") {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Progression />
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("Progression", () => {
  it("renders totals, trend panels, leaderboards, and cross-links", async () => {
    stubFetch()
    renderProgression()

    await waitFor(() => {
      expect(screen.getByTestId("progression-pill")).toHaveTextContent("9 skill events")
    })
    // Trend small-multiples: one panel per non-empty kind (specialty +
    // character_levelup = 2).
    expect(screen.getAllByTestId("trend-panel")).toHaveLength(2)
    // A multi-point series draws a chart; a single-point one shows the total.
    expect(screen.getByTestId("trend-chart")).toBeInTheDocument()
    expect(screen.getByTestId("trend-single")).toBeInTheDocument()
    // Leaderboards prettify skill ids (Blacksmith Skill also appears on the
    // trajectory card, hence getAllByText) and show class completions.
    expect(screen.getAllByText("Blacksmith Skill").length).toBeGreaterThan(0)
    expect(screen.getByText("Smithing Class")).toBeInTheDocument()
    // Warnings surface.
    expect(screen.getByTestId("progression-warnings")).toHaveTextContent("EnrollAction: HTTP 401")
    // Cross-links to the current-state jobs view and crafting provenance.
    expect(screen.getByTestId("link-jobs")).toHaveAttribute("href", "/jobs")
    expect(screen.getByTestId("link-crafting")).toHaveAttribute("href", "/crafting")
  })

  it("expands a trajectory to reveal the event timeline", async () => {
    stubFetch()
    renderProgression()

    await waitFor(() => {
      expect(screen.getAllByTestId("trajectory-card").length).toBe(2)
    })
    // Timeline is hidden until the card is expanded.
    expect(screen.queryByTestId("trajectory-timeline")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /coilysiren/ }))
    const timeline = screen.getByTestId("trajectory-timeline")
    expect(timeline).toBeInTheDocument()
    expect(timeline).toHaveTextContent("character level-ups")
  })

  it("filters trajectories by a ?q= deep link", async () => {
    stubFetch()
    renderProgression("/progression?q=farming")

    await waitFor(() => {
      expect(screen.getByTestId("progression-filter")).toHaveValue("farming")
    })
    // Only the citizen with a Farming specialty survives the filter. The
    // leaderboards are unfiltered, so scope the check to the trajectory cards.
    const cardList = screen.getByTestId("trajectory-cards")
    const cards = within(cardList).getAllByTestId("trajectory-card")
    expect(cards).toHaveLength(1)
    expect(within(cardList).getByText("Citizen #130409")).toBeInTheDocument()
    expect(within(cardList).queryByText("coilysiren")).not.toBeInTheDocument()
  })

  it("shows the empty state when no events are recorded", async () => {
    stubFetch({ ...HISTORY, totalEvents: 0, citizens: [], trends: {} })
    renderProgression()

    await waitFor(() => {
      expect(screen.getByTestId("progression-empty")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("trend-grid")).not.toBeInTheDocument()
  })

  it("degrades when the progression fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")))
    renderProgression()

    await waitFor(() => {
      expect(screen.getByTestId("progression-error")).toBeInTheDocument()
    })
  })
})
