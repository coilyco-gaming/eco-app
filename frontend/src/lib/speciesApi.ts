export interface SpeciesPopulationSample {
  day: number
  value: number
}

export interface SpeciesProfile {
  view: "eco_species"
  name: string
  speciesId: string
  photoDataUri: string | null
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
    `/preview/get_eco_species.json?name=${encodeURIComponent(name)}`,
    { signal },
  )
  if (!response.ok) throw new Error(`species fetch failed: HTTP ${response.status}`)
  return (await response.json()) as SpeciesProfile
}
