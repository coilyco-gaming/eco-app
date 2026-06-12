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
