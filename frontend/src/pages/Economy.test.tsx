import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import Economy from "./Economy"

const SNAPSHOT = {
  server: { description: "Eco via Sirens", category: "Established", sourceUrl: "http://x/info" },
  days_elapsed: 56,
  admin_ok: true,
  kpis: {
    trades_per_day: 23.9,
    trades_total: 1340,
    trades_wow_pct: 0,
    contract_completion_ratio: 0,
    contract_failure_rate: 0,
    contracts_posted: 0,
    contracts_completed: 0,
    contracts_failed: 0,
    loan_default_rate: 0,
    loans_offered: 0,
    loans_accepted: 0,
    loans_repaid: 0,
    loans_defaulted: 0,
    wages_total: 0,
    taxes_paid: 0,
    govt_funds: 0,
    net_tax_flow: 0,
    total_culture: 2254.76,
  },
  health: "healthy",
  narrative: "Economy is healthy",
  economy_desc: "1340 trades, 0 contracts",
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("Economy", () => {
  it("renders KPIs and the crafting cross-link", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(SNAPSHOT), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    )

    render(
      <MemoryRouter initialEntries={["/economy"]}>
        <Economy />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId("health-pill")).toHaveTextContent("Economy is healthy")
    })
    expect(screen.getByText("1,340")).toBeInTheDocument()
    expect(screen.getByText("Trades / day")).toBeInTheDocument()
    expect(screen.getByTestId("link-crafting")).toHaveAttribute("href", "/crafting")
  })

  it("degrades when the snapshot fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")))

    render(
      <MemoryRouter initialEntries={["/economy"]}>
        <Economy />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId("econ-error")).toBeInTheDocument()
    })
  })
})
