// Typed client for the biodiversity + ecoregion match card
// (/preview/get_eco_ecoregion.json).
//
// The endpoint returns ecoregion.build_payload() from
// eco_mcp_app/ecoregion.py: the 12 biome layers with raw + normalized share,
// the top-3 real-world ecoregion matches by cosine similarity, and the
// per-species boom/bust drift strip. Biome colors are chosen server-side so
// the SPA donut and the in-chat MCP card read identically.

export interface Biome {
  name: string
  display: string
  // Raw % of total world area (does NOT sum to 100 — see unclassifiedPercent).
  percent: number
  // Share of *classified* biome area; the donut slices sum these to 100%.
  sharePercent: number
  color: string
  // True for the two derived water slices (coastal/shallow sea, fresh water)
  // appended server-side to reclassify the old grey gap (eco-app#82). They're
  // not real biome layers, so they carry no raster and don't hover-highlight.
  isWater?: boolean
}

export interface EcoregionMatch {
  name: string
  description: string
  // Cosine similarity 0..1 against the normalized world biome vector.
  similarity: number
}

export interface DriftRow {
  name: string
  first: number
  latest: number
  // (latest - first) / first. null when the species grew from a zero
  // baseline (fromZero=true) — an infinite delta the payload can't carry.
  deltaRel: number | null
  fromZero: boolean
}

export interface Drift {
  boom: DriftRow[]
  bust: DriftRow[]
  speciesSeen: number
  speciesWithDrift: number
}

export interface EcoregionSnapshot {
  view: "eco_ecoregion"
  sourceUrl: string
  biomes: Biome[]
  // % of world area with no named biome layer (mountains, shoreline,
  // transitional terrain). biomes' raw percents + this ≈ 100.
  unclassifiedPercent: number
  rawSumPercent: number
  classifiedPercent: number
  ecoregionMatches: EcoregionMatch[]
  drift: Drift
  // False when the admin exporter token is unconfigured or the server
  // rejected it — the drift strip then renders an empty state.
  adminAvailable: boolean
}

export async function fetchEcoregion(signal?: AbortSignal): Promise<EcoregionSnapshot> {
  const resp = await fetch("/preview/get_eco_ecoregion.json", { signal })
  if (!resp.ok) {
    throw new Error(`ecoregion fetch failed: HTTP ${resp.status}`)
  }
  return (await resp.json()) as EcoregionSnapshot
}
