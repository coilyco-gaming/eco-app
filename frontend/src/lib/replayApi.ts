// Typed client for the replay JSON API (eco_replay, the "Kaihronicler" —
// a Chronicler mirror, mounted at /replay/api). One recorded player action
// per row, newest first, plus a mock-data flag for the banner.

export interface ReplayEvent {
  id: number
  unixTime: number
  gameTime: number
  type: string
  citizen: string | null
  body: string
}

export interface ReplayData {
  mockData: boolean
  events: ReplayEvent[]
  total: number
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const resp = await fetch(path, { signal })
  if (!resp.ok) {
    throw new Error(`${path} failed: HTTP ${resp.status}`)
  }
  return (await resp.json()) as T
}

// Fetch a batch of the newest events plus stats and the mock flag in one shot.
// The page filters the fetched batch client-side (mirroring /trades), so one
// generous limit covers the timeline without per-keystroke round-trips.
export async function fetchReplayData(limit = 200, signal?: AbortSignal): Promise<ReplayData> {
  const [meta, events, stats] = await Promise.all([
    getJson<{ mockData: boolean }>("/replay/api/v1/meta", signal),
    getJson<{ events: ReplayEvent[]; count: number }>(
      `/replay/api/v1/events?limit=${limit}`,
      signal,
    ),
    getJson<{ ready: boolean; total: number }>("/replay/api/v1/events/stats", signal),
  ])
  return { mockData: meta.mockData, events: events.events, total: stats.total }
}
