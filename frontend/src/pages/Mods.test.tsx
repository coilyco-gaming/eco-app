import { cleanup, render, screen, within } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"
import { MemoryRouter } from "react-router-dom"
import Mods from "./Mods"

afterEach(cleanup)

function renderMods() {
  return render(
    <MemoryRouter initialEntries={["/mods"]}>
      <Mods />
    </MemoryRouter>,
  )
}

describe("Mod catalog", () => {
  it("lists every canonical catalog group in a compact inventory", () => {
    renderMods()

    expect(within(screen.getByTestId("catalog-app")).getAllByRole("article")).toHaveLength(4)
    expect(within(screen.getByTestId("catalog-public")).getAllByRole("article")).toHaveLength(9)
    expect(within(screen.getByTestId("catalog-server")).getAllByRole("article")).toHaveLength(21)
    expect(within(screen.getByTestId("catalog-nid")).getAllByRole("article")).toHaveLength(11)
  })

  it("links every public upstream and labels entries without a public source", () => {
    renderMods()

    expect(within(screen.getByTestId("public-agricultural")).getByRole("link")).toHaveAttribute(
      "href",
      "https://forgejo.coilysiren.me/coilyco-gaming/eco-mods/src/branch/main/mods/Mods/UserCode/BunWulfAgricultural",
    )
    expect(within(screen.getByTestId("server-beekeeping")).getByRole("link")).toHaveAttribute(
      "href",
      "https://mod.io/g/eco/m/beekeeping",
    )
    expect(screen.getByTestId("server-cavrn")).toHaveTextContent(
      "Discord-only release. No public source page.",
    )
    expect(screen.getByTestId("server-cavrn").querySelector("a")).toBeNull()
  })

  it("keeps each Nid Toolbox module separately visible", () => {
    renderMods()

    expect(screen.getByTestId("nid-core")).toHaveTextContent("Core")
    expect(screen.getByTestId("nid-chat-logger")).toHaveTextContent("Chat Logger")
    expect(screen.getByTestId("nid-timed-messages")).toHaveTextContent("Timed Messages")
    expect(within(screen.getByTestId("nid-laws")).getByRole("link")).toHaveAttribute(
      "href",
      "https://mod.io/g/eco/m/nidtoolbox-full-pack",
    )
  })
})
