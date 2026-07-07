// Formatting helpers for raw Eco server payloads.

// Eco's /info strings carry Unity-style rich text and Eco's own UI markup:
// <color=green>, <style="Culture">, <icon name="Culture" type="nobg">, <b>.
// The web face wants plain text.
const ECO_MARKUP = /<\/?(?:color|style|icon|b|i|size|link)\b[^>]*>/gi

export function stripEcoMarkup(text: string): string {
  return text.replace(ECO_MARKUP, "").replace(/[ \t]+\n/g, "\n").trim()
}

export function formatCount(n: number): string {
  return new Intl.NumberFormat("en-US").format(Math.round(n))
}

// "2026-06-12T11:46:33.611416+00:00" -> "11:46 UTC"
export function formatFetchedAt(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ""
  const hh = String(d.getUTCHours()).padStart(2, "0")
  const mm = String(d.getUTCMinutes()).padStart(2, "0")
  return `${hh}:${mm} UTC`
}

// Age of an event as coarse relative time, e.g. "1 hour ago", "3 days ago".
// Both args are the exporter's `Time` (in-game seconds; one in-game day = 86400s,
// the species-CSV convention social.py folds by), so the gap is a real elapsed
// span. `latest` is the newest event on the surface — the reference "now", since
// `Time` is server seconds, not epoch. Clamped at 0 so clock skew never reads as
// the future. Mirrors the day = Time / 86400 scale used across the social feed.
export function formatRelativeTime(timeS: number, latest: number): string {
  const sec = Math.max(0, Math.round(latest - timeS))
  if (sec < 45) return "just now"
  const units: Array<[number, string]> = [
    [86400, "day"],
    [3600, "hour"],
    [60, "minute"],
  ]
  for (const [size, name] of units) {
    if (sec >= size) {
      const n = Math.round(sec / size)
      return `${n} ${name}${n === 1 ? "" : "s"} ago`
    }
  }
  return `${sec} seconds ago`
}

// A raw in-game day is a float — `Time / 86400` — so 3.5 means "day 3, noon".
// Rendering the bare float ("Day 3.5127") reads as a bug; every day-bearing
// surface should show the whole day AND the clock time folded out of the
// fraction. This is the shared day+hour formatter the site-wide polish sweep
// converges on (eco-app#93); other surfaces still using `Math.floor(day)`
// (e.g. the /trade ledger) can adopt it as they are touched.
export function formatDayHour(day: number | null | undefined): string {
  if (day == null || !Number.isFinite(day)) return "—"
  const whole = Math.floor(day)
  const minutesOfDay = Math.round((day - whole) * 24 * 60)
  // Rounding can push 23:59:30+ up to a full day — carry it so 3.9999 reads
  // "Day 4, 00:00", never "Day 3, 24:00".
  const dayNum = whole + Math.floor(minutesOfDay / (24 * 60))
  const rem = minutesOfDay % (24 * 60)
  const hh = String(Math.floor(rem / 60)).padStart(2, "0")
  const mm = String(rem % 60).padStart(2, "0")
  return `Day ${dayNum}, ${hh}:${mm}`
}

// "BunWulfRawMeatItem" -> "Bun Wulf Raw Meat", "OakSpecies" -> "Oak".
// Mirrors prettify_eco_name in eco_mcp_app/crafting.py.
export function prettifyEcoName(raw: string): string {
  let base = raw
  for (const suffix of ["Item", "Species"]) {
    if (base.endsWith(suffix) && base.length > suffix.length) {
      base = base.slice(0, -suffix.length)
    }
  }
  return base.replace(/(?<!^)(?=[A-Z])/g, " ").trim() || raw
}

// The discord link arrives from the game server's /info payload, i.e. from
// outside this codebase. Only let real web URLs through to href.
export function safeHttpUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined
  try {
    const parsed = new URL(url)
    return parsed.protocol === "https:" || parsed.protocol === "http:"
      ? parsed.toString()
      : undefined
  } catch {
    return undefined
  }
}

// Cycle progress toward the meteor, as a 0-100 integer. The payload gives
// days elapsed and days remaining, so the total is their sum.
export function meteorProgressPercent(daysRunning: number, daysUntilMeteor: number): number {
  const total = daysRunning + daysUntilMeteor
  if (total <= 0) return 0
  return Math.min(100, Math.max(0, Math.round((daysRunning / total) * 100)))
}
