// Typed client for the fused service's JSON surfaces. The SPA talks to the
// same origin in production; in dev, Vite proxies these routes to :4000.

export interface EcoServerInfo {
  description: string
  detailedDescription: string
  category: string
  discord: string | null
  version: string
  language: string
  paused: boolean
  hasPassword: boolean
  adminOnline: boolean
}

export interface EcoPlayers {
  online: number
  onlineNames: string[]
  total: number
  activeAndOnline: number
  peakActive: number
}

export interface EcoWorld {
  size: string
  plants: number
  animals: number
  laws: number
  totalCulture: number
}

export interface EcoCycle {
  daysRunning: number
  daysUntilMeteor: number
  // Real seconds since cycle start (the /info world clock); 1 in-game day = 3600s.
  timeSinceStartS: number
  hasMeteor: boolean
  collaboration: string
  gameSpeed: string
  simulationLevel: string
}

export interface EcoStatus {
  view: "eco_status"
  fetchedAtISO: string
  sourceUrl: string
  server: EcoServerInfo
  players: EcoPlayers
  world: EcoWorld
  cycle: EcoCycle
  economy: { description: string }
  achievements: Array<{ name: string; text: string }>
}

export async function fetchEcoStatus(signal?: AbortSignal): Promise<EcoStatus> {
  const resp = await fetch("/preview.json", { signal })
  if (!resp.ok) {
    throw new Error(`status fetch failed: HTTP ${resp.status}`)
  }
  return (await resp.json()) as EcoStatus
}

// Best-effort JSON fetch for the multi-panel /trade surface: a missing, empty,
// or failed endpoint resolves to null so each panel degrades on its own rather
// than taking the whole page down. The sibling data planes (market, stores,
// logistics, currency, watchers) land independently, so a 404 here is expected
// wiring, not an exceptional error. An aborted fetch also resolves to null —
// the caller unmounts, so there is nothing to surface.
export async function fetchJsonOrNull<T>(url: string, signal?: AbortSignal): Promise<T | null> {
  try {
    const resp = await fetch(url, { signal })
    if (!resp.ok) return null
    return (await resp.json()) as T
  } catch {
    return null
  }
}
