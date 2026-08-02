// Typed client for the civics & governance report (/preview/civics.json).
//
// The endpoint returns CivicsReport.to_dict() from eco_mcp_app/civics.py: the
// history + trend half of the governance surface, folded from the civic action
// exporters (elections, votes, citizenships, settlements) and a handful of
// civics/people daily-count series. Acting citizens are already joined to names
// (proposer / winner / founder / voter), falling back to "Citizen #<id>" when
// the jobs-mod citizens join misses one (eco-app#5). Current-state titles and
// active laws live on the sibling get_government / /server surface — the
// action stream can't derive laws-in-effect.

export interface ElectionEvent {
  subject: string
  proposer: string
  day: number
}

export interface OutcomeEvent {
  subject: string
  winner: string
  day: number
}

export interface DemographicEvent {
  name: string
  day: number
  kind: "joined" | "left"
  settlement: string
}

export interface SettlementEvent {
  subject: string
  founder: string
  day: number
  kind: "settlement" | "homestead"
}

export interface CivicsReport {
  fetchedAtISO: string
  sourceBaseUrl: string
  totalEvents: number
  perActionCounts: Record<string, number>
  electionsStarted: number
  electionsWon: number
  electionsLost: number
  votesCast: number
  abstentions: number
  turnoutRate: number | null
  recentElections: ElectionEvent[]
  recentOutcomes: OutcomeEvent[]
  // [name, votes]
  topVoters: Array<[string, number]>
  citizensGained: number
  citizensLost: number
  netCitizens: number
  residencyMoves: number
  demographicChanges: number
  recentDemographics: DemographicEvent[]
  settlementsFounded: number
  homesteadsStarted: number
  recentSettlements: SettlementEvent[]
  // series name -> [[day, value], ...]
  trend: Record<string, Array<[number, number]>>
  warnings: string[]
}

export async function fetchCivics(signal?: AbortSignal): Promise<CivicsReport> {
  const resp = await fetch("/preview/civics.json", { signal })
  if (!resp.ok) {
    throw new Error(`civics report fetch failed: HTTP ${resp.status}`)
  }
  return (await resp.json()) as CivicsReport
}
