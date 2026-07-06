import { cleanup, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import Economy from "./Economy"

const ECONOMY = {
  server: { description: "Eco via Sirens", category: "Established", sourceUrl: "http://x/info" },
  days_elapsed: 56,
  admin_ok: true,
  kpis: {
    trades_per_day: 23.9,
    trades_total: 1340,
    trades_wow_pct: 0,
    contract_completion_ratio: 0,
    contract_failure_rate: 0,
    contracts_posted: 4,
    contracts_completed: 3,
    contracts_failed: 1,
    loan_default_rate: 0,
    loans_offered: 0,
    loans_accepted: 2,
    loans_repaid: 0,
    loans_defaulted: 0,
    wages_total: 5000,
    taxes_paid: 1200,
    govt_funds: 800,
    net_tax_flow: 400,
    total_culture: 2254.76,
  },
  health: "healthy",
  narrative: "Economy is healthy",
  economy_desc: "1340 trades, 0 contracts",
}

const MONEY = {
  mode: "list",
  days_elapsed: 56,
  admin_ok: true,
  narrative: "Currency market: 2 active currencies, 1 minted / 1 personal, money supply 12,000.",
  economy_desc: "1340 trades",
  money: {
    activeCurrencies: 2,
    personalWealth: 9000,
    governmentHoldings: 3000,
    totalSupply: 12000,
    tradeValue7d: 1200,
    hasSupplyData: true,
  },
  series: {
    personalWealth: [
      [0, 8000],
      [86400, 9000],
    ],
    governmentHoldings: [
      [0, 2000],
      [86400, 3000],
    ],
    activeCurrencies: [
      [0, 2],
      [86400, 2],
    ],
    trades7d: [
      [0, 500],
      [86400, 1200],
    ],
  },
  currencies: [
    {
      name: "Sirens",
      type: "minted",
      isMinted: true,
      mintedAmount: 1500,
      mintEvents: 2,
      tradeCount: 20,
      tradeVolume: 900,
      createdBy: "Kai",
      holders: {
        reachable: true,
        note: "",
        accountsCounted: 3,
        totalHoldings: 9250,
        list: [
          { account: "Treasury", holder: null, balance: 6000 },
          { account: "Kai's Personal Account", holder: "Kai", balance: 2500 },
          { account: "Salt's Personal Account", holder: "Salt", balance: 750 },
        ],
      },
    },
    {
      name: "Salt Credits",
      type: "personal",
      isMinted: false,
      mintedAmount: 0,
      mintEvents: 0,
      tradeCount: 4,
      tradeVolume: 60,
      createdBy: "Salt",
      holders: { reachable: false, note: "mod not deployed", accountsCounted: 0, totalHoldings: 0, list: [] },
    },
  ],
  minted: [],
  personal: [],
  counts: { total: 2, minted: 1, personal: 1 },
  holders_reachable: true,
  holders_unavailable_note: "Live top-holder balances need the exporter mod.",
  warnings: [],
  fetched_at_iso: "2026-07-06T00:00:00+00:00",
}

function jsonResponse(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

const NOT_FOUND = Symbol("404")

function stub(overrides: { economy?: unknown; money?: unknown } = {}) {
  const planes: Record<string, unknown> = {
    "get_eco_economy.json": overrides.economy ?? ECONOMY,
    "currency.json": overrides.money ?? MONEY,
  }
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const u = String(url)
      const key = Object.keys(planes).find((k) => u.includes(k))
      const payload = key ? planes[key] : null
      if (payload === NOT_FOUND || payload == null) {
        return Promise.resolve(new Response("not found", { status: 404 }))
      }
      return Promise.resolve(jsonResponse(payload))
    }),
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function renderEconomy() {
  return render(
    <MemoryRouter initialEntries={["/economy"]}>
      <Economy />
    </MemoryRouter>,
  )
}

describe("Economy", () => {
  it("renders money supply, currencies, wealth, trade flows, and cross-links", async () => {
    stub()
    renderEconomy()

    await waitFor(() => {
      expect(screen.getByTestId("health-pill")).toHaveTextContent("Economy is healthy")
    })

    // Money supply headline + the two-series supply chart.
    const supply = screen.getByTestId("money-supply")
    expect(within(supply).getByText("12,000")).toBeInTheDocument()
    expect(within(supply).getByTestId("trend-chart")).toBeInTheDocument()

    // Currency roster, ranked by trade volume.
    const roster = screen.getByTestId("currency-roster")
    expect(within(roster).getByText("Sirens")).toBeInTheDocument()
    expect(within(roster).getByText(/Salt Credits/)).toBeInTheDocument()

    // Wealth distribution picks the dominant reachable currency (Sirens).
    const wealth = screen.getByTestId("wealth-distribution")
    expect(wealth).toHaveTextContent("Wealth in Sirens")
    expect(within(wealth).getByTestId("wealth-concentration")).toBeInTheDocument()
    expect(within(wealth).getByText("Treasury")).toBeInTheDocument()

    // Trade flows still carry the KPI numbers.
    expect(screen.getByText("1,340")).toBeInTheDocument()
    expect(screen.getByText("Trades / day")).toBeInTheDocument()

    expect(screen.getByTestId("link-crafting")).toHaveAttribute("href", "/crafting")
    expect(screen.getByTestId("link-trade")).toHaveAttribute("href", "/trade")
  })

  it("still renders trade flows when the money plane is absent", async () => {
    stub({ money: NOT_FOUND })
    renderEconomy()

    await waitFor(() => {
      expect(screen.getByTestId("trade-flows")).toBeInTheDocument()
    })
    // Money-only sections drop out; the KPI economy card survives.
    expect(screen.queryByTestId("money-supply")).not.toBeInTheDocument()
    expect(screen.queryByTestId("currencies")).not.toBeInTheDocument()
    expect(screen.getByText("1,340")).toBeInTheDocument()
  })

  it("shows the holders-unavailable note when the exporter mod is undeployed", async () => {
    const money = {
      ...MONEY,
      holders_reachable: false,
      currencies: MONEY.currencies.map((c) => ({
        ...c,
        holders: { reachable: false, note: "mod not deployed", accountsCounted: 0, totalHoldings: 0, list: [] },
      })),
    }
    stub({ money })
    renderEconomy()

    await waitFor(() => {
      expect(screen.getByTestId("wealth-unavailable")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("wealth-distribution")).not.toBeInTheDocument()
  })

  it("degrades when the economy snapshot fetch fails", async () => {
    stub({ economy: NOT_FOUND, money: NOT_FOUND })
    renderEconomy()

    await waitFor(() => {
      expect(screen.getByTestId("econ-error")).toBeInTheDocument()
    })
  })
})
