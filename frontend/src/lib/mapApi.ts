// Typed client for the live world-map plane (/preview-map.json → get_map,
// with include_biomes so the SPA gets per-biome rasters for hover-highlight).
//
// The endpoint returns map.build_map_payload() from eco_mcp_app/map.py: the
// base world preview inlined as a data URI, one SVG polygon spec per property
// deed (already seam-split + owner-coloured server-side), and — SPA-only — a
// biomeLayers list of per-biome raster overlays keyed to the ecoregion donut's
// biome names, so hovering a biome highlights where it sits on the map (#82).

export interface MapPolygon {
  owner: string
  deed: string
  fill: string
  stroke: string
  // SVG `points` attribute: space-separated "x,y" pairs in renderSize space.
  points: string
  // True for a deed translated across the world seam so the viewBox can clip
  // it. Those carry coordinates outside 0..renderSize, negatives included, so
  // never fit a viewport to them (eco-app#229).
  seamCopy: boolean
}

export interface MapBiomeLayer {
  // Matches an EcoregionSnapshot biome `name` (e.g. "OceanBiome").
  name: string
  display: string
  color: string
  // The biome's coverage raster, inlined so CSP needs no external origin.
  dataUri: string
}

export interface MapPayload {
  view: "eco_map"
  sourceUrl: string | null
  // World extent; the SPA scales hotspot world-coords by renderSize/worldDim.
  worldDim: { x: number; y: number; z: number }
  renderSize: number
  gifDataUri: string
  pollutionDataUri: string | null
  biomeLayers: MapBiomeLayer[]
  polygons: MapPolygon[]
  deedCount: number
  polygonCount: number
  seamCopyCount: number
  seamNote: string
  ownerCount: number
  owners: string[]
  owner_colors: Record<string, string>
  owner_strokes: Record<string, string>
}

export async function fetchMap(signal?: AbortSignal): Promise<MapPayload> {
  const resp = await fetch("/preview-map.json", { signal })
  if (!resp.ok) {
    throw new Error(`map fetch failed: HTTP ${resp.status}`)
  }
  return (await resp.json()) as MapPayload
}
