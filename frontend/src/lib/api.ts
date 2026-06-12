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
