// Typed client for the progression / skills-history surface
// (/preview/progression.json).
//
// The endpoint returns ProgressionHistory.to_dict() from
// eco_mcp_app/progression.py: per-citizen skill trajectories (the history
// behind the current skills the jobs surface shows), server-wide per-day
// trends per event kind, and the leaderboards that fall out of them. Citizen
// ids are already joined to names, falling back to "Citizen #<id>" when the
// jobs-mod citizens join misses one (eco-app#5).

export interface ProgressionEvent {
  day: number
  time: number
  // Normalized event kind: profession | specialty | specialty_loss |
  // specialty_levelup | character_levelup | class | enroll.
  kind: string
  skill: string
  pretty: string
  level: number | null
}

export interface HeldSpecialty {
  name: string
  pretty: string
  level: number | null
}

export interface NamedSkill {
  name: string
  pretty: string
}

export interface CitizenTrajectory {
  name: string
  eventCount: number
  firstDay: number
  lastDay: number
  characterLevel: number | null
  levelUpCount: number
  professions: NamedSkill[]
  specialties: HeldSpecialty[]
  // Newest events first, capped server-side.
  timeline: ProgressionEvent[]
}

export interface ProgressionHistory {
  fetchedAtISO: string
  sourceBaseUrl: string
  totalEvents: number
  perActionCounts: Record<string, number>
  // Only populated when the request asks for it — the timelines run to ~266 KB
  // and are off by default so MCP callers reach the summary layer instead of a
  // capped-out error (eco-app#232). The SPA opts in below.
  citizens: CitizenTrajectory[]
  citizensAvailable: number
  citizensReturned: number
  // kind -> [[day, count], ...] sorted by day.
  trends: Record<string, Array<[number, number]>>
  // [name, gainedCount] leaderboards.
  bySpecialty: Array<[string, number]>
  byProfession: Array<[string, number]>
  classCompletions: Array<[string, number]>
  // [citizenName, levelUpCount]
  topLevelers: Array<[string, number]>
  firstSpecialtyGains: Array<{
    skill: string
    pretty: string
    day: number
    time: number
  }>
  // Best-effort discovered progression daily series: name -> [[day, value]].
  dailySeries: Record<string, Array<[number, number]>>
  warnings: string[]
}

// Human labels for the normalized event kinds (mirror KIND_LABELS in
// eco_mcp_app/progression.py) — used by the SPA to render trend titles and
// timeline rows without leaking the wire-format enum.
export const KIND_LABELS: Record<string, string> = {
  profession: "professions gained",
  specialty: "specialties gained",
  specialty_loss: "specialties dropped",
  specialty_levelup: "specialty level-ups",
  character_levelup: "character level-ups",
  class: "classes completed",
  enroll: "enrollments",
}

// Order the trend small-multiples render in — most narratively useful first.
export const TREND_ORDER: string[] = [
  "specialty",
  "specialty_levelup",
  "character_levelup",
  "profession",
  "class",
  "enroll",
  "specialty_loss",
]

export async function fetchProgressionHistory(
  signal?: AbortSignal,
): Promise<ProgressionHistory> {
  const resp = await fetch("/preview/progression.json?include_timelines=1", { signal })
  if (!resp.ok) {
    throw new Error(`progression history fetch failed: HTTP ${resp.status}`)
  }
  return (await resp.json()) as ProgressionHistory
}
