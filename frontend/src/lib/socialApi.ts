// Typed client for the community activity surface (/preview/social.json).

export interface NewArrival {
  label: string
  day: number
}

export interface ReputationEdge {
  source: string
  target: string
  amount: number
  count: number
}

export interface SocialSurface {
  fetchedAtISO: string
  sourceBaseUrl: string
  redacted: boolean
  perTypeCounts: Record<string, number>
  totalReputationTransfers: number
  totalFirstLogins: number
  totalPlayEvents: number
  playByDay: Array<[number, number]>
  firstLoginsByDay: Array<[number, number]>
  newArrivals: NewArrival[]
  reputationEdges: ReputationEdge[]
  topReputationGivers: Array<[string, number]>
  topReputationReceivers: Array<[string, number]>
  warnings: string[]
}

export async function fetchSocial(signal?: AbortSignal): Promise<SocialSurface> {
  const response = await fetch("/preview/social.json", { signal })
  if (!response.ok) {
    throw new Error(`community activity fetch failed: HTTP ${response.status}`)
  }
  return (await response.json()) as SocialSurface
}
