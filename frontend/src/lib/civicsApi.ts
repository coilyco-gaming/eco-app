// Typed client for the civics & governance report (/preview/civics.json).
//
// The endpoint returns CivicsReport.to_dict() from eco_mcp_app/civics.py: the
// history + trend half of the governance surface, folded from the civic action
// exporters (elections, votes, citizenships, settlements) and a handful of
// civics/people daily-count series. Acting citizens are already joined to names
// (proposer / winner / founder / voter). An id the jobs-mod citizens join
// misses comes back as null with the raw id in the matching `*Id` field, never
// as a "Citizen #<id>" person — some of those ids turned out to be election
// titles rather than people (eco-app#223). Current-state titles and
// active laws live on the sibling get_government / /server surface — the
// action stream can't derive laws-in-effect.

export interface ElectionEvent {
  subject: string | null
  subjectId: string | null
  proposer: string | null
  proposerId: string | null
  day: number
}

export interface OutcomeEvent {
  subject: string | null
  subjectId: string | null
  winner: string | null
  winnerId: string | null
  day: number
}

export interface DemographicEvent {
  name: string | null
  nameId: string | null
  day: number
  kind: "joined" | "left"
  settlement: string | null
  settlementId: string | null
}

export interface SettlementEvent {
  subject: string | null
  subjectId: string | null
  founder: string | null
  founderId: string | null
  day: number
  kind: "settlement" | "foundation" | "homestead"
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
  // Staked foundations, which may never become settlements. Counted apart from
  // foundings, which used to be summed into one number (eco-app#225).
  settlementFoundationsPlaced: number
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
