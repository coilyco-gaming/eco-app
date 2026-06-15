import { useEffect, useState } from "react"
import Layout from "../components/Layout"
import { type ClimateSnapshot, fetchClimate } from "../lib/climateApi"

interface Stat {
  label: string
  value: string
  detail?: string
  tone?: "add" | "remove"
}

// Signed integer ppm with thousands separators, e.g. "+12,687" / "-28,989".
function signedPpm(n: number): string {
  const sign = n > 0 ? "+" : n < 0 ? "−" : ""
  return `${sign}${new Intl.NumberFormat("en-US").format(Math.round(Math.abs(n)))}`
}

function signed(n: number, digits = 2): string {
  const sign = n > 0 ? "+" : n < 0 ? "−" : ""
  return `${sign}${Math.abs(n).toFixed(digits)}`
}

export default function Climate() {
  const [snap, setSnap] = useState<ClimateSnapshot | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchClimate(controller.signal)
      .then(setSnap)
      .catch((err) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err))
      })
    return () => controller.abort()
  }, [])

  const atmosphere: Stat[] = snap
    ? [
        {
          label: "CO₂",
          value: snap.co2.current != null ? `${Math.round(snap.co2.current)} ppm` : "—",
          detail:
            snap.co2.change_pct != null
              ? `${signed(snap.co2.change_pct)}% since cycle start`
              : undefined,
        },
        {
          label: "Avg temperature",
          value: snap.temperature.current != null ? `${snap.temperature.current.toFixed(1)} °C` : "—",
          detail:
            snap.temperature.risen != null && snap.temperature.risen !== 0
              ? `${signed(snap.temperature.risen)} °C this cycle`
              : undefined,
        },
        {
          label: "Sea level",
          value: snap.sea_level.current != null ? `${snap.sea_level.current.toFixed(2)} m` : "—",
          detail:
            snap.effects.sea_level.risen_m != null && snap.effects.sea_level.risen_m !== 0
              ? `${signed(snap.effects.sea_level.risen_m)} m this cycle`
              : undefined,
        },
        {
          label: "Ground pollution",
          value: snap.pollution.current != null ? `${snap.pollution.current.toFixed(1)}%` : "—",
          detail: snap.pollution.source !== "none" ? `source: ${snap.pollution.source}` : undefined,
        },
      ]
    : []

  const b = snap?.breakdown
  const sources: Stat[] =
    b?.has_data && b.pollution && b.animals && b.plants && b.net_per_day != null
      ? [
          {
            label: "From pollution",
            value: `${signedPpm(b.pollution.lifetime)} ppm`,
            detail: `${signed(b.pollution.per_day)} ppm/day`,
            tone: "add",
          },
          {
            label: "From animals",
            value: `${signedPpm(b.animals.lifetime)} ppm`,
            detail: `${signed(b.animals.per_day)} ppm/day`,
            tone: "add",
          },
          {
            label: "From plants",
            value: `${signedPpm(b.plants.lifetime)} ppm`,
            detail: `${signed(b.plants.per_day)} ppm/day`,
            tone: "remove",
          },
          {
            label: "Net change",
            value: `${signed(b.net_per_day)} ppm/day`,
            detail: b.net_per_day < 0 ? "CO₂ falling" : b.net_per_day > 0 ? "CO₂ rising" : "steady",
            tone: b.net_per_day <= 0 ? "remove" : "add",
          },
        ]
      : []

  const eff = snap?.effects
  const warnTone = snap && snap.status !== "stable" && snap.status !== "unknown"

  return (
    <Layout fetchedAtISO={snap?.fetched_at_iso}>
      <section className="hero hero-compact">
        <p className="hero-kicker">Climate</p>
        <h1 className="hero-title">
          What the <span className="accent">air is doing</span> to the world
        </h1>
        {snap && (
          <p
            className={`hero-pill${warnTone ? " hero-pill-warn" : ""}`}
            data-testid="climate-pill"
          >
            <span className="pulse-dot" aria-hidden="true" />
            {snap.narrative}
          </p>
        )}
        {!snap && error && (
          <p className="hero-pill hero-pill-muted" data-testid="climate-error">
            climate snapshot unavailable right now
          </p>
        )}
      </section>

      {snap && (
        <>
          {snap.explainer.length > 0 && (
            <section>
              <h2 className="section-title">What this means &amp; what to expect</h2>
              <ul className="explainer" data-testid="explainer">
                {snap.explainer.map((line, i) => (
                  <li key={i}>{line}</li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <h2 className="section-title">Atmosphere</h2>
            <div className="stats">
              {atmosphere.map((s) => (
                <div className="stat" key={s.label}>
                  <p className="stat-value">{s.value}</p>
                  <p className="stat-label">{s.label}</p>
                  {s.detail && <p className="stat-detail">{s.detail}</p>}
                </div>
              ))}
            </div>
          </section>

          {sources.length > 0 && (
            <section>
              <h2 className="section-title">CO₂ sources &amp; sinks</h2>
              <p className="intro">
                <span>
                  Where the atmosphere's CO₂ comes from and goes — lifetime totals with each
                  source's current daily push. Pollution and animals add CO₂, plants remove it.
                </span>
              </p>
              <div className="stats">
                {sources.map((s) => (
                  <div className={`stat stat-${s.tone}`} key={s.label}>
                    <p className="stat-value">{s.value}</p>
                    <p className="stat-label">{s.label}</p>
                    {s.detail && <p className="stat-detail">{s.detail}</p>}
                  </div>
                ))}
              </div>
            </section>
          )}

          {eff && eff.co2_now != null && (
            <section>
              <h2 className="section-title">CO₂ effects</h2>
              <p className="intro">
                <span>Eco's default climate ruleset — a server admin can retune these.</span>
              </p>
              <div className="stats">
                <div className="stat">
                  <p className="stat-value">Temperature rise</p>
                  <p className="stat-detail">
                    +1 °C for every {eff.temperature.ppm_per_degree} ppm past{" "}
                    {eff.temperature.threshold_ppm} ppm.
                    {eff.temperature.headroom_ppm != null && eff.temperature.headroom_ppm > 0 && (
                      <>
                        {" "}
                        <strong>
                          {Math.round(eff.temperature.headroom_ppm)} ppm of headroom.
                        </strong>
                      </>
                    )}
                  </p>
                </div>
                <div className="stat">
                  <p className="stat-value">Sea level rise</p>
                  <p className="stat-detail">
                    +1 m for every {eff.sea_level.ppm_per_meter} ppm past{" "}
                    {eff.sea_level.threshold_ppm} ppm.
                    {eff.co2_peak != null && (eff.sea_level.peak_drives_m ?? 0) > 0 && (
                      <>
                        {" "}
                        <strong>Cycle peak {Math.round(eff.co2_peak)} ppm.</strong>
                      </>
                    )}
                  </p>
                </div>
              </div>
            </section>
          )}
        </>
      )}
    </Layout>
  )
}
