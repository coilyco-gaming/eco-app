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
  it("lists the live, linked use-case cards", () => {
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
    expect(screen.getByTestId("use-price").closest("a")).toHaveAttribute("href", "/uses/price")
    expect(screen.getByTestId("use-shop-check").closest("a")).toHaveAttribute(
      "href",
      "/uses/shop-check",
    )
    expect(screen.getByTestId("use-recipe-graph").closest("a")).toHaveAttribute(
      "href",
      "/recipes",
    )
    expect(screen.getByTestId("use-profession-value").closest("a")).toHaveAttribute(
      "href",
      "/jobs",
    )
    expect(screen.queryByText(/coming soon/i)).not.toBeInTheDocument()
  })
})
