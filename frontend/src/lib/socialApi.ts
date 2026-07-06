// Typed client for the social / chat surface (/preview/social.json).
//
// The endpoint returns SocialSurface.to_dict() from eco_mcp_app/social.py. It is
// a **public** path, so it is always redacted: player names are stable
// `player-<hash>` handles and message bodies are scrubbed of real names. The
// `redacted` flag says so explicitly. Names-in-the-clear is an operator-gated
// MCP mode only, never reachable through this endpoint (eco-app#63).

export interface ChatSample {
  day: number
  // Event time in in-game seconds (exporter `Time`). Rendered as age relative to
  // the surface's `latestTimeS`, so the feed reads "1 hour ago" not "day 3".
  timeS: number
  author: string
  channel: string
  message: string
}

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
  // Newest event time (in-game seconds) across the surface — the reference the
  // chat feed measures each message's age against.
  latestTimeS: number
  perTypeCounts: Record<string, number>
  totalChat: number
  totalReputationTransfers: number
  totalFirstLogins: number
  totalPlayEvents: number
  // [day, count]
  chatByDay: Array<[number, number]>
  playByDay: Array<[number, number]>
  firstLoginsByDay: Array<[number, number]>
  // [channel, messageCount]
  chatByChannel: Array<[string, number]>
  // [handle, messageCount]
  topChatters: Array<[string, number]>
  newArrivals: NewArrival[]
  reputationEdges: ReputationEdge[]
  // [handle, amount]
  topReputationGivers: Array<[string, number]>
  topReputationReceivers: Array<[string, number]>
  recentChat: ChatSample[]
  warnings: string[]
}

export async function fetchSocial(signal?: AbortSignal): Promise<SocialSurface> {
  const resp = await fetch("/preview/social.json", { signal })
  if (!resp.ok) {
    throw new Error(`social surface fetch failed: HTTP ${resp.status}`)
  }
  return (await resp.json()) as SocialSurface
}
