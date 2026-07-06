// Typed client for the hidden per-user dossier surface (eco-app#80).
//
// The page lives at `/users/<hex>` where <hex> is the base16 of the username.
// It is hidden (no nav link) but NOT password-protected. The SPA decodes the
// hex segment back to the username and asks the backend for a dossier — every
// field the exporters carry about that one player. The `/users` index consumes
// `/preview/users.json`, the "list every user, never a truncated top-N" roster.

// base16 (hex) of a username's UTF-8 bytes. Lowercase, no separators — the
// path segment. `encodeUserHex(decodeUserHex(h)) === h` for any valid hex.
export function encodeUserHex(name: string): string {
  return Array.from(new TextEncoder().encode(name))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
}

// Recover the username from a `/users/<hex>` path segment. Throws on a
// malformed segment (odd length or a non-hex character) so the page can show a
// clear "bad link" state rather than a mojibake username.
export function decodeUserHex(hex: string): string {
  const clean = hex.trim().toLowerCase()
  if (clean.length === 0 || clean.length % 2 !== 0 || /[^0-9a-f]/.test(clean)) {
    throw new Error(`not a base16 username segment: "${hex}"`)
  }
  const bytes = new Uint8Array(clean.length / 2)
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(clean.slice(i * 2, i * 2 + 2), 16)
  }
  return new TextDecoder().decode(bytes)
}

export interface JobsSection {
  active: boolean
  lastSeenISO: string | null
  specialties: Array<{ specialty: string; level: number; active: boolean }>
}

export interface TradeRow {
  buyer: string
  seller: string
  shopOwner: string
  item?: string
  quantity?: number
  currency?: string
  currencyAmount?: number
  unitPrice?: number | null
  day?: number
  direction?: string
  [key: string]: unknown
}

export interface TradesSection {
  currencySpent: number
  currencyEarned: number
  trades: TradeRow[]
}

export interface CraftingSection {
  events: number
}

export interface CivicsSection {
  votesCast: number
  elections: Array<{ subject: string; day: number; role: "proposed" | "won" }>
  demographics: Array<{ kind: string; day: number; settlement: string }>
  settlements: Array<{ subject: string; day: number; kind: string }>
}

export interface CurrencyHolding {
  currency: string
  balance: number
  account: string
}

export interface CurrencySection {
  holdings: CurrencyHolding[]
}

export interface ProgressionSection {
  levelUpCount: number
  trajectory?: {
    name: string
    eventCount?: number
    firstDay?: number
    lastDay?: number
    characterLevel?: number | null
    levelUpCount?: number
    professions?: Array<{ name: string; pretty: string }>
    specialties?: Array<{ name: string; pretty: string; level: number | null }>
    timeline?: Array<{
      day: number
      kind: string
      skill: string
      pretty: string
      level: number | null
    }>
  }
}

export interface WorldSection {
  shaperEvents: number
  pollutionEvents: number
}

export interface UserDossier {
  username: string
  found: boolean
  fetchedAtISO: string
  available: Record<string, boolean>
  jobs: JobsSection | null
  trades: TradesSection | null
  crafting: CraftingSection | null
  civics: CivicsSection | null
  currency: CurrencySection | null
  progression: ProgressionSection | null
  world: WorldSection | null
  roster: string[]
  warnings: string[]
}

export interface UsersIndex {
  fetchedAtISO: string
  users: string[]
  available: Record<string, boolean>
}

export async function fetchUserDossier(
  username: string,
  signal?: AbortSignal,
): Promise<UserDossier> {
  const resp = await fetch(`/preview/user.json?name=${encodeURIComponent(username)}`, { signal })
  if (!resp.ok) {
    throw new Error(`user dossier fetch failed: HTTP ${resp.status}`)
  }
  return (await resp.json()) as UserDossier
}

export async function fetchUsersIndex(signal?: AbortSignal): Promise<UsersIndex> {
  const resp = await fetch("/preview/users.json", { signal })
  if (!resp.ok) {
    throw new Error(`users index fetch failed: HTTP ${resp.status}`)
  }
  return (await resp.json()) as UsersIndex
}
