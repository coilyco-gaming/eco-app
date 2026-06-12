import { describe, expect, it } from "vitest"
import {
  formatCount,
  formatFetchedAt,
  meteorProgressPercent,
  safeHttpUrl,
  stripEcoMarkup,
} from "./format"

describe("stripEcoMarkup", () => {
  it("strips Unity color tags", () => {
    expect(stripEcoMarkup("<color=green>Eco</color> via <color=blue>Sirens</color>")).toBe(
      "Eco via Sirens",
    )
  })

  it("strips Eco style and icon tags, keeping inner text", () => {
    expect(
      stripEcoMarkup(
        '<style="Culture"><icon name="Culture" type="nobg"></icon>122.35 Culture</style>',
      ),
    ).toBe("122.35 Culture")
  })

  it("leaves plain text and newlines alone", () => {
    expect(stripEcoMarkup("Cycle 13\n\n60-day meteor")).toBe("Cycle 13\n\n60-day meteor")
  })
})

describe("formatCount", () => {
  it("groups thousands and rounds floats", () => {
    expect(formatCount(64342)).toBe("64,342")
    expect(formatCount(2254.7598)).toBe("2,255")
  })
})

describe("formatFetchedAt", () => {
  it("renders an HH:MM UTC stamp", () => {
    expect(formatFetchedAt("2026-06-12T11:46:33.611416+00:00")).toBe("11:46 UTC")
  })

  it("returns empty string for garbage", () => {
    expect(formatFetchedAt("not-a-date")).toBe("")
  })
})

describe("safeHttpUrl", () => {
  it("passes real web URLs through", () => {
    expect(safeHttpUrl("https://discord.gg/example")).toBe("https://discord.gg/example")
  })

  it("rejects hostile or malformed schemes", () => {
    expect(safeHttpUrl("javascript:alert(1)")).toBeUndefined()
    expect(safeHttpUrl("data:text/html,hi")).toBeUndefined()
    expect(safeHttpUrl("not a url")).toBeUndefined()
    expect(safeHttpUrl(null)).toBeUndefined()
    expect(safeHttpUrl("")).toBeUndefined()
  })
})

describe("meteorProgressPercent", () => {
  it("computes elapsed share of the cycle", () => {
    expect(meteorProgressPercent(56, 3)).toBe(95)
  })

  it("clamps degenerate inputs", () => {
    expect(meteorProgressPercent(0, 0)).toBe(0)
    expect(meteorProgressPercent(10, -20)).toBe(0)
  })
})
