// Typed client for the jobs JSON API (eco_spec_tracker, mounted at /jobs/api).

export interface ProfessionStat {
  profession: string
  active: number
  covered: number
  total: number
  players: string[]
}

export interface SpecialtyHolder {
  player: string
  level: number
  active: boolean
  roles: string[]
}

export interface SpecialtyStat {
  specialty: string
  profession: string
  active: number
  covered: number
  total: number
  holders: SpecialtyHolder[]
}

export interface PlayerSpecialty {
  specialty: string
  level: number
  active: boolean
}

export interface PlayerRow {
  name: string
  active: boolean
  roles: string[]
  specialties: PlayerSpecialty[]
}

export interface JobsData {
  mockData: boolean
  professions: ProfessionStat[]
  specialties: SpecialtyStat[]
  players: PlayerRow[]
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const resp = await fetch(path, { signal })
  if (!resp.ok) {
    throw new Error(`${path} failed: HTTP ${resp.status}`)
  }
  return (await resp.json()) as T
}

export async function fetchJobsData(signal?: AbortSignal): Promise<JobsData> {
  const [meta, professions, specialties, players] = await Promise.all([
    getJson<{ mockData: boolean }>("/jobs/api/v1/meta", signal),
    getJson<ProfessionStat[]>("/jobs/api/v1/professions", signal),
    getJson<SpecialtyStat[]>("/jobs/api/v1/specialties", signal),
    getJson<PlayerRow[]>("/jobs/api/v1/players", signal),
  ])
  return { mockData: meta.mockData, professions, specialties, players }
}
