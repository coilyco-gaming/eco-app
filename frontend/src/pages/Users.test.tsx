import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import { encodeUserHex } from "../lib/usersApi"
import Users from "./Users"

const INDEX = {
  fetchedAtISO: "2026-06-12T13:00:00+00:00",
  users: ["Citizen #999", "coilysiren", "ekans"],
  available: { jobs: true, trades: true },
}

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("Users index", () => {
  it("lists every user with a link to their hex dossier", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse(INDEX))))
    render(
      <MemoryRouter>
        <Users />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId("users-pill")).toHaveTextContent("3 users")
    })
    const links = screen.getAllByTestId("user-link")
    expect(links).toHaveLength(3)
    // Names route to /users/<base16-of-name>, including the awkward "Citizen #999".
    expect(links[0]).toHaveAttribute("href", `/users/${encodeUserHex("Citizen #999")}`)
    expect(screen.getByText("coilysiren")).toBeInTheDocument()
  })

  it("shows an empty state when no users are recorded", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(jsonResponse({ ...INDEX, users: [] }))))
    render(
      <MemoryRouter>
        <Users />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId("users-empty")).toBeInTheDocument()
    })
  })

  it("degrades when the index fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")))
    render(
      <MemoryRouter>
        <Users />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByTestId("users-error")).toBeInTheDocument()
    })
  })
})
