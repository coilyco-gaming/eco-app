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
    specialties: [
      { specialty: "Basic Carpentry", level: 5, active: true },
      { specialty: "Hunting", level: 2, active: true },
    ],
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
        // A raw float day — the whole point of eco-app#93 is that this renders
        // as "Day 3, 12:00", never "3.5".
        day: 3.5,
        time: 3.5 * 86400,
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
  warnings: ["currency holdings list the top holders per currency"],
}

function offer(over: Record<string, unknown>) {
  return {
    store: "Store",
    owner: "someone",
    storeKey: "k",
    item: "X",
    itemPretty: "X",
    currency: "Credit",
    side: "sell",
    price: 0,
    quantity: 0,
    source: "live",
    lastDay: null,
    ...over,
  }
}

// The market spine the summary reads — the same /preview/logistics.json the
// /trade page consumes. coilysiren has a live sell offer (Iron Ingot) and a
// live buy order (Wood), and the market has a supply gap (Nails).
const LOGISTICS = {
  view: "logistics",
  fetchedAtISO: "2026-06-12T13:00:00+00:00",
  sourceBaseUrl: "",
  live: true,
  totalOffers: 3,
  totalStores: 2,
  cheapest: [
    {
      item: "IronIngotItem",
      itemPretty: "Iron Ingot",
      currency: "Credit",
      offers: [
        offer({ owner: "coilysiren", item: "IronIngotItem", itemPretty: "Iron Ingot", side: "sell", price: 12, quantity: 40, store: "Coily Forge" }),
        offer({ owner: "ekans", item: "IronIngotItem", itemPretty: "Iron Ingot", side: "sell", price: 14, quantity: 8, store: "Ekans Wares" }),
      ],
    },
  ],
  resale: [
    {
      item: "WoodItem",
      itemPretty: "Wood",
      currency: "Credit",
      offers: [
        offer({ owner: "coilysiren", item: "WoodItem", itemPretty: "Wood", side: "buy", price: 3, quantity: 100, store: "Coily Buys" }),
      ],
    },
  ],
  arbitrage: [],
  supplyGaps: [
    {
      item: "NailItem",
      itemPretty: "Nails",
      currency: "Credit",
      reason: "no_supply",
      sellerCount: 0,
      buyerCount: 2,
      demandQty: 50,
      supplyQty: 0,
      buyPrice: 5,
      cheapestSell: null,
      median: null,
      overMedianPct: null,
      buyers: [],
    },
  ],
  warnings: [],
}

const STORES = {
  view: "stores",
  fetchedAtISO: "2026-06-12T13:00:00+00:00",
  sourceBaseUrl: "",
  totalTrades: 5,
  perTypeCounts: {},
  stores: [],
  traders: [
    {
      name: "coilysiren",
      citizenId: "1",
      tradeCount: 5,
      totalVolume: 500,
      sellVolume: 300,
      buyVolume: 200,
      uniqueCounterparties: 2,
      lastDay: 3,
      storesOperated: [],
      topSells: [{ item: "IronIngotItem", pretty: "Iron Ingot", tradeCount: 2, volume: 300, quantity: 40, avgUnitPrice: 12 }],
      topBuys: [],
    },
  ],
  totalStores: 0,
  totalTraders: 1,
  warnings: [],
}

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

// Route each preview plane to its fixture; the dossier page now fans out to the
// dossier, logistics, and stores planes just like /trade.
function routedFetch(url: string, spine = true): Response {
  if (url.includes("/preview/user.json")) return jsonResponse(DOSSIER)
  if (spine && url.includes("/preview/logistics.json")) return jsonResponse(LOGISTICS)
  if (spine && url.includes("/preview/stores.json")) return jsonResponse(STORES)
  // A missing spine plane 404s — the summary degrades, the dossier stands.
  return new Response("not found", { status: 404 })
}

function stubFetch(spine = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn((u: RequestInfo | URL) => Promise.resolve(routedFetch(String(u), spine))),
  )
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
    stubFetch()
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

  it("renders day-bearing rows as day + hour, never a bare float", async () => {
    stubFetch()
    renderUser(encodeUserHex("coilysiren"))

    await waitFor(() => {
      expect(screen.getByTestId("user-trades")).toBeInTheDocument()
    })
    // day 3.5 -> "Day 3, 12:00", not "3.5".
    expect(screen.getByTestId("user-trades")).toHaveTextContent("Day 3, 12:00")
    expect(screen.getByTestId("user-trades")).not.toHaveTextContent("3.5")
    // Civics + timeline days carry their hour too (whole days read "00:00").
    expect(screen.getByTestId("user-civics-events")).toHaveTextContent("Day 4, 00:00")
    expect(screen.getByTestId("user-timeline")).toHaveTextContent("Day 3, 00:00")
  })

  it("leads with an actionable summary from the market spine", async () => {
    stubFetch()
    renderUser(encodeUserHex("coilysiren"))

    await waitFor(() => {
      expect(screen.getByTestId("user-selling")).toBeInTheDocument()
    })
    // What they're selling / buying right now, owner-matched from logistics.
    expect(screen.getByTestId("user-selling")).toHaveTextContent("Iron Ingot")
    expect(screen.getByTestId("user-selling")).toHaveTextContent("12 Credit")
    expect(screen.getByTestId("user-buying")).toHaveTextContent("Wood")
    // Best positioned: their strongest specialty crossed with a market gap.
    expect(screen.getByTestId("user-strengths")).toHaveTextContent("Basic Carpentry")
    expect(screen.getByTestId("user-gaps")).toHaveTextContent("Nails")
    // Recent activity in relative time, not a day float.
    expect(screen.getByTestId("user-recent")).toHaveTextContent("bought")
    expect(screen.getByTestId("user-recent")).toHaveTextContent("Iron Ingot")
  })

  it("degrades the summary but keeps the dossier when the spine is missing", async () => {
    stubFetch(false) // logistics + stores 404
    renderUser(encodeUserHex("coilysiren"))

    await waitFor(() => {
      expect(screen.getByTestId("user-trades")).toBeInTheDocument()
    })
    // No live offers, but the stores fallback is gone too — so the summary still
    // renders from the dossier's own specialties + recent activity.
    expect(screen.queryByTestId("user-selling")).not.toBeInTheDocument()
    expect(screen.getByTestId("user-strengths")).toHaveTextContent("Basic Carpentry")
    expect(screen.getByTestId("user-recent")).toHaveTextContent("bought")
    // The full per-surface panels below are untouched.
    expect(screen.getByTestId("user-holdings")).toHaveTextContent("Credit")
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
    vi.stubGlobal(
      "fetch",
      vi.fn((u: RequestInfo | URL) =>
        Promise.resolve(
          String(u).includes("/preview/user.json")
            ? jsonResponse(empty)
            : new Response("not found", { status: 404 }),
        ),
      ),
    )
    renderUser(encodeUserHex("ghost"))

    await waitFor(() => {
      expect(screen.getByTestId("user-not-found")).toBeInTheDocument()
    })
    // No actionable summary for a player with no data.
    expect(screen.queryByTestId("user-selling")).not.toBeInTheDocument()
  })

  it("degrades when the dossier fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")))
    renderUser(encodeUserHex("coilysiren"))

    await waitFor(() => {
      expect(screen.getByTestId("user-error")).toBeInTheDocument()
    })
  })
})
