import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import PagePassword from "./PagePassword"

function renderGate() {
  return render(
    <MemoryRouter>
      <PagePassword>
        <div data-testid="protected">secret surface</div>
      </PagePassword>
    </MemoryRouter>,
  )
}

// A fetch stub that answers GET /page-auth (the required-check) and
// POST /page-auth (the verify) from the given config.
function stubFetch({ required, accept }: { required: boolean; accept?: string }) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as { password: string }
        return new Response(JSON.stringify({ ok: body.password === accept }), { status: 200 })
      }
      return new Response(JSON.stringify({ required }), { status: 200 })
    }),
  )
}

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  localStorage.clear()
})

describe("PagePassword", () => {
  it("renders children straight through when no password is required", async () => {
    stubFetch({ required: false })
    renderGate()
    await waitFor(() => expect(screen.getByTestId("protected")).toBeInTheDocument())
  })

  it("shows the prompt and unlocks on the right password", async () => {
    stubFetch({ required: true, accept: "open-sesame" })
    renderGate()

    await waitFor(() => expect(screen.getByTestId("page-gate")).toBeInTheDocument())
    expect(screen.queryByTestId("protected")).not.toBeInTheDocument()

    fireEvent.change(screen.getByTestId("gate-input"), { target: { value: "open-sesame" } })
    fireEvent.click(screen.getByTestId("gate-submit"))

    await waitFor(() => expect(screen.getByTestId("protected")).toBeInTheDocument())
    expect(localStorage.getItem("eco-app:page-unlocked")).toBe("1")
  })

  it("keeps the gate up and reports a mismatch on the wrong password", async () => {
    stubFetch({ required: true, accept: "open-sesame" })
    renderGate()

    await waitFor(() => expect(screen.getByTestId("page-gate")).toBeInTheDocument())
    fireEvent.change(screen.getByTestId("gate-input"), { target: { value: "nope" } })
    fireEvent.click(screen.getByTestId("gate-submit"))

    await waitFor(() => expect(screen.getByTestId("gate-error")).toBeInTheDocument())
    expect(screen.queryByTestId("protected")).not.toBeInTheDocument()
  })

  it("skips the prompt when the browser already unlocked", async () => {
    localStorage.setItem("eco-app:page-unlocked", "1")
    stubFetch({ required: true, accept: "open-sesame" })
    renderGate()
    await waitFor(() => expect(screen.getByTestId("protected")).toBeInTheDocument())
    expect(screen.queryByTestId("page-gate")).not.toBeInTheDocument()
  })
})
