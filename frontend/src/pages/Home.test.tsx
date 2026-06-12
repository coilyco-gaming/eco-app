import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import Home from "./Home"
import { SAMPLE_STATUS } from "../test/fixtures"

function renderHome() {
  return render(
    <MemoryRouter>
      <Home />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe("Home", () => {
  it("renders the directory with live badges", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(SAMPLE_STATUS), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    )

    renderHome()

    expect(screen.getByTestId("dir-server")).toHaveAttribute("href", "/server")
    expect(screen.getByTestId("dir-jobs")).toHaveAttribute("href", "/jobs/")
    expect(screen.getByTestId("dir-preview")).toHaveAttribute("href", "/preview")

    await waitFor(() => {
      expect(screen.getByTestId("server-badges")).toHaveTextContent("3d to meteor")
    })
    expect(screen.getByTestId("server-badges")).toHaveTextContent("1 online")
    expect(screen.getByRole("link", { name: "Join the Discord" })).toHaveAttribute(
      "href",
      "https://discord.gg/example",
    )
  })

  it("renders the full directory even when the snapshot fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")))

    renderHome()

    await waitFor(() => {
      expect(screen.getByTestId("dir-jobs")).toBeInTheDocument()
    })
    expect(screen.getByTestId("dir-preview")).toBeInTheDocument()
    expect(screen.queryByTestId("server-badges")).not.toBeInTheDocument()
  })
})
