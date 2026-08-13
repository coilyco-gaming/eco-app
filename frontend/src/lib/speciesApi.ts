export interface SpeciesPopulationSample {
  day: number
  value: number
}

export interface SpeciesProfile {
  view: "eco_species"
  name: string
  speciesId: string
  // Only populated when the caller asks for it. The inlined image is ~285 KB,
  // so it is off by default to keep MCP responses under their cap
  // (eco-app#230); the SPA opts in below. photoUrl is always present.
  photoDataUri: string | null
  photoUrl: string | null
  photoAttribution: string | null
  wikiExtract: string | null
  wikiUrl: string | null
  source: "inat" | "wikipedia" | "none"
  taxonomy: Array<{ rank: string; name: string }>
  conservationStatus: string | null
  population: SpeciesPopulationSample[]
  populationFirst: number | null
  populationLatest: number | null
  populationDelta: number | null
  error: string | null
}

export async function fetchSpecies(name: string, signal?: AbortSignal): Promise<SpeciesProfile> {
  const response = await fetch(
    // limit=0: the species page charts the whole population curve; the
    // bounded default thins it for MCP callers (eco-app#256).
    `/preview/get_species.json?name=${encodeURIComponent(name)}&include_image=1&limit=0`,
    { signal },
  )
  if (!response.ok) throw new Error(`species fetch failed: HTTP ${response.status}`)
  return (await response.json()) as SpeciesProfile
}
