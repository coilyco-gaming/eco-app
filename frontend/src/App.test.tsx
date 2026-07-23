import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import App from "./App"

afterEach(cleanup)

describe("SPA routes", () => {
  it("serves the production-mod reference on a direct /mods route", () => {
    window.history.pushState({}, "", "/mods")
    render(<App />)

    expect(screen.getByRole("heading", { name: "The C# mods behind the site" })).toBeInTheDocument()
  })
})
