import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { MemoryRouter } from "react-router-dom"
import Uses from "./Uses"

function renderUses() {
  return render(
    <MemoryRouter initialEntries={["/uses"]}>
      <Uses />
    </MemoryRouter>,
  )
}

afterEach(cleanup)

describe("Uses hub", () => {
  it("lists the four demand-side pages as live, linked cards", () => {
    renderUses()
    expect(screen.getByTestId("use-demand").closest("a")).toHaveAttribute("href", "/uses/demand")
    expect(screen.getByTestId("use-buy-sell").closest("a")).toHaveAttribute(
      "href",
      "/uses/buy-sell",
    )
    expect(screen.getByTestId("use-arbitrage").closest("a")).toHaveAttribute(
      "href",
      "/uses/arbitrage",
    )
    expect(screen.getByTestId("use-shop-check").closest("a")).toHaveAttribute(
      "href",
      "/uses/shop-check",
    )
  })

  it("shows the recipe-dependent use cases as muted, unlinked coming-soon cards", () => {
    renderUses()
    const soon = screen.getAllByTestId("use-soon")
    expect(soon.length).toBeGreaterThan(0)
    // Coming-soon cards are static divs, not links.
    soon.forEach((card) => expect(card.closest("a")).toBeNull())
  })
})
