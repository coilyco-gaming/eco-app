import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import Layout from "../components/Layout"
import { type DriftRow, type EcoregionSnapshot, fetchEcoregion } from "../lib/ecoregionApi"
import { formatCount } from "../lib/format"

// Donut geometry — matches the in-chat MCP card so the two surfaces read the
// same. A stroke-dashed circle draws each slice; offset walks around the ring.
const DONUT_R = 40
const DONUT_C = 2 * Math.PI * DONUT_R
const UNCLASSIFIED_COLOR = "#3a4a40"

interface Slice {
  key: string
  label: string
  color: string
  percent: number
  length: number
  offset: number
}

// Build ring slices from raw biome percents plus the unclassified remainder,
// so the donut sums to a full 100% of world area (issue acceptance: raw
// percentages with an "unclassified" slice filling the gap to 100%).
function buildSlices(snap: EcoregionSnapshot): Slice[] {
  const slices: Slice[] = []
  let cursor = 0
  const push = (key: string, label: string, color: string, percent: number) => {
    if (percent <= 0) return
    const length = DONUT_C * (percent / 100)
    slices.push({ key, label, color, percent, length, offset: -DONUT_C * (cursor / 100) })
    cursor += percent
  }
  for (const b of snap.biomes) push(b.name, b.display, b.color, b.percent)
  push("__unclassified", "Unclassified / mixed terrain", UNCLASSIFIED_COLOR, snap.unclassifiedPercent)
  return slices
}

function Donut({ snap }: { snap: EcoregionSnapshot }) {
  const slices = buildSlices(snap)
  return (
    <svg
      className="eco-donut"
      viewBox="-50 -50 100 100"
      width="200"
      height="200"
      role="img"
      aria-label="Biome composition of the world"
    >
      {slices.map((s) => (
        <circle
          key={s.key}
          cx="0"
          cy="0"
          r={DONUT_R}
          fill="none"
          stroke={s.color}
          strokeWidth="14"
          strokeDasharray={`${s.length.toFixed(3)} ${(DONUT_C - s.length).toFixed(3)}`}
          strokeDashoffset={s.offset.toFixed(3)}
          transform="rotate(-90)"
        >
          <title>
            {s.label}: {Math.round(s.percent)}%
          </title>
        </circle>
      ))}
      <text x="0" y="-2" textAnchor="middle" className="eco-donut-num">
        {Math.round(snap.rawSumPercent)}%
      </text>
      <text x="0" y="7" textAnchor="middle" className="eco-donut-sub">
        classified
      </text>
    </svg>
  )
}

// Boom/bust column. Bars scale to the loudest mover in the column so a Day-3
// world with tiny deltas still shows relative shape. A from-zero grower
// (deltaRel === null) shows "new" and pins the bar full.
function DriftColumn({
  title,
  tone,
  rows,
}: {
  title: string
  tone: "add" | "remove"
  rows: DriftRow[]
}) {
  const magnitude = (d: DriftRow) => (d.deltaRel === null ? 1 : Math.abs(d.deltaRel))
  const max = Math.max(...rows.map(magnitude), 1e-9)
  return (
    <div className="eco-drift-col">
      <h3 className={`eco-drift-head eco-drift-${tone}`}>{title}</h3>
      {rows.length === 0 ? (
        <p className="empty-note">No species {tone === "add" ? "trending up" : "trending down"}.</p>
      ) : (
        <ul className="rank-rows">
          {rows.map((d) => (
            <li key={d.name}>
              <div className="rank-row" data-testid={`drift-${tone}-row`}>
                <span className="rank-name">{d.name}</span>
                <span className={`rank-count eco-delta-${tone}`}>
                  {d.deltaRel === null
                    ? "new"
                    : `${d.deltaRel > 0 ? "+" : ""}${Math.round(d.deltaRel * 100)}%`}
                </span>
                <span className="rank-detail">
                  {formatCount(Math.round(d.first))} → {formatCount(Math.round(d.latest))}
                </span>
                <span
                  className={`rank-bar eco-bar-${tone}`}
                  style={{ width: `${(magnitude(d) / max) * 100}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function Ecoregion() {
  const [snap, setSnap] = useState<EcoregionSnapshot | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchEcoregion(controller.signal)
      .then(setSnap)
      .catch((err) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err))
      })
    return () => controller.abort()
  }, [])

  const topMatch = snap?.ecoregionMatches[0]

  return (
    <Layout>
      <section className="hero hero-compact">
        <p className="hero-kicker">Biodiversity &amp; ecoregion</p>
        <h1 className="hero-title">
          Where this world sits <span className="accent">on Earth</span>
        </h1>
        {snap && (
          <p className="hero-pill" data-testid="eco-pill">
            <span className="pulse-dot" aria-hidden="true" />
            {topMatch
              ? `Closest to ${topMatch.name} · ${Math.round(snap.rawSumPercent)}% of the map is a named biome`
              : `${Math.round(snap.rawSumPercent)}% of the map is a named biome`}
          </p>
        )}
        {!snap && error && (
          <p className="hero-pill hero-pill-muted" data-testid="eco-error">
            biodiversity snapshot unavailable right now
          </p>
        )}
      </section>

      {snap && (
        <>
          <section>
            <h2 className="section-title">Biome composition</h2>
            <p className="intro">
              <span>
                Share of the whole map covered by each biome. They don't sum to 100% — mountains,
                shoreline, and transitional terrain aren't tagged to any named biome, so{" "}
                {Math.round(snap.unclassifiedPercent)}% of the world falls into the grey
                "unclassified" slice.
              </span>
            </p>
            <div className="eco-donut-row">
              <Donut snap={snap} />
              <ul className="eco-legend" data-testid="eco-legend">
                {snap.biomes
                  .filter((b) => b.percent > 0)
                  .map((b) => (
                    <li key={b.name}>
                      <span className="eco-swatch" style={{ background: b.color }} />
                      <span className="eco-legend-label">{b.display}</span>
                      <span className="eco-legend-pct">{Math.round(b.percent)}%</span>
                    </li>
                  ))}
                <li>
                  <span className="eco-swatch" style={{ background: UNCLASSIFIED_COLOR }} />
                  <span className="eco-legend-label">Unclassified / mixed terrain</span>
                  <span className="eco-legend-pct">{Math.round(snap.unclassifiedPercent)}%</span>
                </li>
              </ul>
            </div>
          </section>

          <section>
            <h2 className="section-title">Closest real-world ecoregions</h2>
            <p className="intro">
              <span>
                The map's biome mix, normalized to shape, matched against WWF terrestrial
                ecoregions by cosine similarity.
              </span>
            </p>
            {snap.ecoregionMatches.length > 0 ? (
              <ol className="eco-matches" data-testid="eco-matches">
                {snap.ecoregionMatches.map((m) => (
                  <li key={m.name}>
                    <div className="eco-match-head">
                      <span className="eco-match-name">{m.name}</span>
                      <span className="eco-match-sim">{m.similarity.toFixed(2)}</span>
                    </div>
                    <p className="eco-match-desc">{m.description}</p>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="empty-note">No ecoregion fixture loaded.</p>
            )}
          </section>

          <section>
            <h2 className="section-title">Biodiversity drift</h2>
            {!snap.adminAvailable ? (
              <p className="empty-note" data-testid="eco-drift-admin">
                Population drift needs the server's admin exporter — configure the API key to see
                which species are booming and busting.
              </p>
            ) : snap.drift.speciesWithDrift === 0 ? (
              <p className="empty-note" data-testid="eco-drift-minimal">
                Drift minimal so far — tracked {snap.drift.speciesSeen} species with no net change
                yet this cycle.
              </p>
            ) : (
              <div className="eco-drift" data-testid="eco-drift">
                <DriftColumn title="Boom" tone="add" rows={snap.drift.boom} />
                <DriftColumn title="Bust" tone="remove" rows={snap.drift.bust} />
              </div>
            )}
          </section>

          <section className="dir-cards">
            <Link className="dir-card" to="/climate" data-testid="link-climate">
              <h3>Climate →</h3>
              <p>What CO₂, temperature, and sea level are doing to the world these species live in.</p>
            </Link>
          </section>
        </>
      )}
    </Layout>
  )
}
