// Typed client for the world / industry activity surface
// (/preview/world.json → get_eco_world). byCitizen / byPolluter carry display
// names joined from the jobs mod's /api/v1/citizens surface, falling back to
// "Citizen #<id>" when a name is missing (eco-app#5, eco-app#62).

export interface WorldCategory {
  key: string
  label: string
  events: number
  volume: number
}

export interface WorldTimelineDay {
  day: number
  counts: Record<string, number>
}

export interface WorldHotspot {
  x: number
  z: number
  events: number
}

export interface WorldActivity {
  view: string
  fetchedAtISO: string
  sourceBaseUrl: string
  totalEvents: number
  perActionCounts: Record<string, number>
  categories: WorldCategory[]
  categoryKeys: string[]
  timeline: WorldTimelineDay[]
  byCitizen: Array<[string, number]>
  byPolluter: Array<[string, number]>
  byObject: Array<[string, number]>
  hotspots: WorldHotspot[]
  warnings: string[]
}

export async function fetchWorld(signal?: AbortSignal): Promise<WorldActivity> {
  const resp = await fetch("/preview/world.json", { signal })
  if (!resp.ok) {
    throw new Error(`world activity fetch failed: HTTP ${resp.status}`)
  }
  return (await resp.json()) as WorldActivity
}
