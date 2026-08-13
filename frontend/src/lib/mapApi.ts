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

export interface MapDeed {
  deed: string
  owner: string
  centroid: { x: number; z: number }
  bbox: { minX: number; minZ: number; maxX: number; maxZ: number }
  areaBlocks: number
  vertexCount: number
  seamCrossing: boolean
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
  // Present when the payload was built with geometry (the SPA route always is;
  // the MCP tool makes it opt-in via include_geometry, eco-app#264).
  polygons: MapPolygon[]
  geometryIncluded: boolean
  // One styling representation, keyed by owner. Polygons reference it by
  // `owner` rather than repeating fill/stroke on every entry.
  ownerStyles: Record<string, { fill: string; stroke: string }>
  deedCount: number
  polygonCount: number
  // Per-deed centroid / bounding box / approximate area, in world blocks.
  deeds: MapDeed[]
  deedsNote: string
  seamCopyCount: number
  seamNote: string
  ownerCount: number
  owners: string[]
}

export async function fetchMap(signal?: AbortSignal): Promise<MapPayload> {
  const resp = await fetch("/preview-map.json", { signal })
  if (!resp.ok) {
    throw new Error(`map fetch failed: HTTP ${resp.status}`)
  }
  return (await resp.json()) as MapPayload
}
