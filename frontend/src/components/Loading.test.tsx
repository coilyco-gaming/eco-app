import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import Loading from "./Loading"

afterEach(() => cleanup())

describe("Loading", () => {
  it("renders the default label as a status region", () => {
    render(<Loading />)
    const el = screen.getByTestId("loading")
    expect(el).toHaveTextContent("Loading…")
    expect(el).toHaveAttribute("role", "status")
  })

  it("honours a custom label and testid", () => {
    render(<Loading label="Reading the chronicle…" testid="replay-loading" />)
    expect(screen.getByTestId("replay-loading")).toHaveTextContent("Reading the chronicle…")
  })
})
