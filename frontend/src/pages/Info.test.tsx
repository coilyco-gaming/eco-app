import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import Info from "./Info"
import { SAMPLE_STATUS } from "../test/fixtures"

function renderServer() {
  return render(
    <MemoryRouter initialEntries={["/info"]}>
      <Info />
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

describe("Info", () => {
  it("renders the live snapshot from /preview.json", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(SAMPLE_STATUS), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    )

    renderServer()

    await waitFor(() => {
      expect(screen.getByTestId("meteor-count")).toHaveTextContent("3 days until the meteor")
    })
    expect(screen.getByTestId("live-pill")).toHaveTextContent("1 online now")
    expect(screen.getByTestId("online-player-list")).toHaveTextContent("coilysiren")
    expect(screen.getByText("Eco via Sirens | Cycle 13")).toBeInTheDocument()
    expect(screen.getByText("64,342")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Join the Discord" })).toHaveAttribute(
      "href",
      "https://discord.gg/example",
    )
  })

  it("keeps the shell useful when the snapshot fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")))

    renderServer()

    await waitFor(() => {
      expect(screen.getByTestId("live-pill")).toHaveTextContent("live snapshot unavailable")
    })
    expect(screen.getByRole("link", { name: "Eco on Steam" })).toBeInTheDocument()
    expect(screen.queryByTestId("meteor-count")).not.toBeInTheDocument()
  })
})
