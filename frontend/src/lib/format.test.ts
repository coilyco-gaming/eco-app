import { describe, expect, it } from "vitest"
import {
  formatCount,
  formatDayHour,
  formatEventDay,
  formatFetchedAt,
  formatRelative,
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

describe("formatEventDay", () => {
  it("folds the fractional exporter day into a clock time", () => {
    expect(formatEventDay(3.5)).toBe("Day 3, 12:00")
    expect(formatEventDay(0)).toBe("Day 0, 00:00")
    expect(formatEventDay(12)).toBe("Day 12, 00:00")
    expect(formatEventDay(2.25)).toBe("Day 2, 06:00")
  })

  it("carries a rounded-up fraction into the next whole day", () => {
    // 3.99999 rounds to 24:00 of day 3 — must read as day 4, 00:00.
    expect(formatEventDay(3.99999)).toBe("Day 4, 00:00")
  })

  it("dashes out missing / non-finite days", () => {
    expect(formatEventDay(null)).toBe("—")
    expect(formatEventDay(undefined)).toBe("—")
    expect(formatEventDay(Number.NaN)).toBe("—")
    expect(formatEventDay(Number.POSITIVE_INFINITY)).toBe("—")
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

describe("formatDayHour", () => {
  it("folds world-clock seconds into an in-game day and hour", () => {
    // 3600s = one in-game day; 150s = one in-game hour.
    expect(formatDayHour(0)).toBe("day 0, 0h")
    expect(formatDayHour(3600)).toBe("day 1, 0h")
    expect(formatDayHour(3600 + 150)).toBe("day 1, 1h")
    // 56 days + 12 in-game hours -> 56 * 3600 + 1800 = 203400.
    expect(formatDayHour(203400)).toBe("day 56, 12h")
  })

  it("clamps negatives so skew never reads before the cycle start", () => {
    expect(formatDayHour(-10)).toBe("day 0, 0h")
  })
})

describe("formatRelative", () => {
  it("reads the real elapsed gap in coarse units", () => {
    expect(formatRelative(100, 100)).toBe("just now")
    expect(formatRelative(0, 60)).toBe("1 minute ago")
    expect(formatRelative(0, 3600)).toBe("1 hour ago")
    expect(formatRelative(0, 7200)).toBe("2 hours ago")
    expect(formatRelative(0, 86400)).toBe("1 day ago")
  })

  it("clamps a future timestamp to just now", () => {
    expect(formatRelative(100, 50)).toBe("just now")
  })
})
