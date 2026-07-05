// Typed client for the climate snapshot (/preview/get_eco_climate.json).
//
// The endpoint returns compute_climate_payload() from eco_mcp_app/climate.py:
// headline status + narrative, four atmosphere KPIs, the CO2 source/sink
// breakdown, the CO2-effects mechanic, and a plain-language explainer — the
// same data the in-game pollution-machine status panel surfaces.

export interface ClimateKpi {
  current: number | null
  dataset_name: string | null
  series: [number, number][]
}

export interface Co2Kpi extends ClimateKpi {
  change_pct: number | null
}

export interface SeaLevelKpi extends ClimateKpi {
  change_pct: number | null
  rate_per_day: number
}

export interface TemperatureKpi extends ClimateKpi {
  risen: number | null
  rate_per_day: number
}

export interface PollutionKpi extends ClimateKpi {
  source: string
  layer_summary: string | null
}

export interface SourceLine {
  lifetime: number
  per_day: number
}

export interface Breakdown {
  has_data: boolean
  pollution?: SourceLine
  animals?: SourceLine
  plants?: SourceLine
  net_per_day?: number
}

export interface EffectAxis {
  threshold_ppm: number
  headroom_ppm: number | null
  peak_drives_c?: number
  peak_drives_m?: number
  ppm_per_degree?: number
  ppm_per_meter?: number
  current_c?: number | null
  current_m?: number | null
  risen_c?: number | null
  risen_m?: number | null
}

export interface Effects {
  co2_now: number | null
  co2_peak: number | null
  min_floor_ppm: number
  at_floor: boolean
  // "live" when the telemetry mod's /api/v1/climate-settings endpoint supplied
  // the thresholds (real per-server values), "default" when it was absent and
  // we fell back to Eco's documented defaults. Drives the ruleset disclaimer.
  source: "live" | "default"
  temperature: EffectAxis
  sea_level: EffectAxis
  // Extra Eco climate knobs, present only when the server emits them.
  pollution_multiplier?: number
  max_co2_per_day_from_animals?: number
  min_co2_per_day_from_plants?: number
}

export interface EarthMatch {
  year: number
  ppm: number
  note: string
}

export interface ClimateSnapshot {
  server: { description: string; category: string | null; sourceUrl: string | null }
  days_elapsed: number
  admin_ok: boolean
  status: "stable" | "warming" | "critical" | "unknown"
  narrative: string
  co2: Co2Kpi
  sea_level: SeaLevelKpi
  pollution: PollutionKpi
  temperature: TemperatureKpi
  breakdown: Breakdown
  effects: Effects
  explainer: string[]
  earth_match: EarthMatch | null
  fetched_at_iso: string
}

export async function fetchClimate(signal?: AbortSignal): Promise<ClimateSnapshot> {
  const resp = await fetch("/preview/get_eco_climate.json", { signal })
  if (!resp.ok) {
    throw new Error(`climate fetch failed: HTTP ${resp.status}`)
  }
  return (await resp.json()) as ClimateSnapshot
}
