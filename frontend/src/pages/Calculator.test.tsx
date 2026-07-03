import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { MemoryRouter } from "react-router-dom"
import Calculator from "./Calculator"

function renderCalculator() {
  return render(
    <MemoryRouter>
      <Calculator />
    </MemoryRouter>,
  )
}

afterEach(cleanup)

describe("Calculator", () => {
  it("opens the Eco Gnome calculator and preserves attribution", () => {
    renderCalculator()

    expect(screen.getByRole("heading", { name: /Eco Gnome/i })).toBeInTheDocument()
    expect(screen.getByTestId("calc-open")).toHaveAttribute("href", "https://eco-gnome.com")
    expect(screen.getByTestId("calc-attribution")).toHaveTextContent("MIT-licensed")
  })

  it("spells out the self-host + Sirens-data roadmap", () => {
    renderCalculator()

    const roadmap = screen.getByTestId("calc-roadmap")
    expect(roadmap).toHaveTextContent(/self-host/i)
    expect(roadmap).toHaveTextContent(/DataExporter/i)
  })
})
