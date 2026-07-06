import { useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"
import Layout from "../components/Layout"
import Loading from "../components/Loading"
import { type DriftRow, type EcoregionSnapshot, fetchEcoregion } from "../lib/ecoregionApi"
import { formatCount, prettifyEcoName } from "../lib/format"
import { type MapPayload, fetchMap } from "../lib/mapApi"
import { type WorldActivity, fetchWorld } from "../lib/worldApi"

// ---------------------------------------------------------------------------
// Donut geometry — shared with the in-chat MCP ecoregion card so the two
// surfaces read identically. A stroke-dashed circle draws each slice.
// ---------------------------------------------------------------------------
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

// Raw biome percents plus the unclassified remainder, so the donut sums to a
// full 100% of world area. Water slices (eco-app#82) already ride in
// snap.biomes, so they slot in alongside the named biomes automatically.
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
      aria-label="Biome and water composition of the world"
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
        {Math.round(snap.classifiedPercent)}%
      </text>
      <text x="0" y="7" textAnchor="middle" className="eco-donut-sub">
        classified
      </text>
    </svg>
  )
}

// Boom/bust column, unchanged from the old /ecoregion page.
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

// ---------------------------------------------------------------------------
// World-mutation timeline — carried over from the old /world page.
// ---------------------------------------------------------------------------
const CATEGORY_COLORS: Record<string, string> = {
  construction: "#3987e5",
  objects: "#199e70",
  roads: "#c98500",
  garbage: "#008300",
  explosions: "#9085e9",
  pollution: "#e66767",
  extraction: "#d55181",
}
const FALLBACK_COLOR = "#7da18a"

function catColor(key: string): string {
  return CATEGORY_COLORS[key] ?? FALLBACK_COLOR
}

function labelFor(world: WorldActivity, key: string): string {
  return world.categories.find((c) => c.key === key)?.label ?? key
}

function MutationTimeline({ world }: { world: WorldActivity }) {
  const days = world.timeline
  if (days.length === 0) {
    return <p className="empty-note">No time-stamped events to chart yet.</p>
  }
  const keys = world.categoryKeys
  const width = 720
  const height = 240
  const padL = 44
  const padR = 12
  const padT = 16
  const padB = 28
  const plotW = width - padL - padR
  const plotH = height - padT - padB

  const totals = days.map((d) => keys.reduce((s, k) => s + (d.counts[k] ?? 0), 0))
  const maxTotal = Math.max(...totals, 1)
  const dayNums = days.map((d) => d.day)
  const minDay = Math.min(...dayNums)
  const maxDay = Math.max(...dayNums)

  const slot = plotW / days.length
  const barW = Math.max(2, slot * 0.7)

  return (
    <svg
      className="mutation-timeline"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="World-mutation events per in-game day, stacked by category"
      data-testid="mutation-timeline"
    >
      <line x1={padL} y1={padT + plotH} x2={width - padR} y2={padT + plotH} className="axis-grid" />
      <line x1={padL} y1={padT} x2={width - padR} y2={padT} className="axis-grid" />
      <text x={padL - 6} y={padT + 4} textAnchor="end" className="axis-label">
        {formatCount(maxTotal)}
      </text>
      <text x={padL - 6} y={padT + plotH} textAnchor="end" className="axis-label">
        0
      </text>
      {days.map((d, i) => {
        const x = padL + i * slot + (slot - barW) / 2
        let cursor = padT + plotH
        return (
          <g key={d.day}>
            {keys.map((k) => {
              const v = d.counts[k] ?? 0
              if (v <= 0) return null
              const h = (v / maxTotal) * plotH
              const segH = Math.max(0, h - 2)
              const y = cursor - h
              cursor -= h
              return (
                <rect key={k} x={x} y={y} width={barW} height={segH} rx={1} fill={catColor(k)}>
                  <title>
                    Day {d.day} · {labelFor(world, k)}: {formatCount(v)}
                  </title>
                </rect>
              )
            })}
          </g>
        )
      })}
      <text x={padL} y={height - 6} className="axis-label">
        day {minDay}
      </text>
      <text x={width - padR} y={height - 6} textAnchor="end" className="axis-label">
        day {maxDay}
      </text>
    </svg>
  )
}

function TimelineLegend({ world }: { world: WorldActivity }) {
  return (
    <ul className="chart-legend" data-testid="timeline-legend">
      {world.categories.map((c) => (
        <li key={c.key}>
          <span className="legend-swatch" style={{ background: catColor(c.key) }} aria-hidden="true" />
          <span className="legend-label">{c.label}</span>
          <span className="legend-count">{formatCount(c.events)}</span>
        </li>
      ))}
    </ul>
  )
}

interface RankRow {
  name: string
  count: number
}

function RankList({
  rows,
  emptyNote,
  prettify = false,
  testid,
}: {
  rows: RankRow[]
  emptyNote: string
  prettify?: boolean
  testid: string
}) {
  if (rows.length === 0) {
    return <p className="empty-note">{emptyNote}</p>
  }
  const max = Math.max(...rows.map((r) => r.count), 1)
  return (
    <ul className="rank-rows" data-testid={testid}>
      {rows.map((r) => (
        <li key={r.name}>
          <div className="rank-row" data-testid={`${testid}-row`}>
            <span className="rank-name">{prettify ? prettifyEcoName(r.name) : r.name}</span>
            <span className="rank-count">{formatCount(r.count)}</span>
            <span className="rank-bar" style={{ width: `${(r.count / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  )
}

// ---------------------------------------------------------------------------
// The map itself — base preview + per-biome highlight rasters + deed polygons
// + activity-hotspot overlay, all in one renderSize-space SVG frame (#82).
// ---------------------------------------------------------------------------
function WorldMap({
  map,
  world,
  hoveredBiome,
}: {
  map: MapPayload
  world: WorldActivity | null
  hoveredBiome: string | null
}) {
  const size = map.renderSize
  const wx = map.worldDim.x || size
  const wz = map.worldDim.z || size
  const hotspots = world?.hotspots ?? []
  const maxHot = Math.max(...hotspots.map((h) => h.events), 1)

  return (
    <div className="map-figure">
      <div className="map-frame" data-testid="map-frame" style={{ aspectRatio: "1 / 1" }}>
        <img className="map-base" src={map.gifDataUri} alt="Eco world preview" draggable={false} />
        {map.pollutionDataUri && (
          <img className="map-pollution" src={map.pollutionDataUri} alt="" aria-hidden="true" />
        )}
        {/* Per-biome highlight rasters — invisible until their biome is hovered. */}
        {map.biomeLayers.map((b) => (
          <img
            key={b.name}
            className="map-biome"
            src={b.dataUri}
            alt=""
            aria-hidden="true"
            data-testid={`map-biome-${b.name}`}
            style={{ opacity: hoveredBiome === b.name ? 0.92 : 0 }}
          />
        ))}
        <svg
          className="map-overlay"
          viewBox={`0 0 ${size} ${size}`}
          preserveAspectRatio="xMidYMid meet"
          xmlns="http://www.w3.org/2000/svg"
          data-testid="map-overlay"
        >
          {map.polygons.map((p, i) => (
            <polygon
              key={`${p.deed}-${i}`}
              points={p.points}
              fill={p.fill}
              stroke={p.stroke}
              strokeWidth={1.5}
            >
              <title>
                {p.deed} — {p.owner}
              </title>
            </polygon>
          ))}
          {/* Activity hotspots overlaid on the real map — radius by event count. */}
          {hotspots.map((h) => {
            const cx = (h.x / wx) * size
            const cy = (h.z / wz) * size
            const r = 4 + (h.events / maxHot) * 16
            return (
              <circle
                key={`${h.x},${h.z}`}
                cx={cx}
                cy={cy}
                r={r}
                className="map-hotspot"
                data-testid="map-hotspot"
              >
                <title>
                  ({h.x}, {h.z}) · {formatCount(h.events)} events
                </title>
              </circle>
            )
          })}
        </svg>
      </div>
      <p className="map-meta" data-testid="map-meta">
        {map.deedCount} deed{map.deedCount === 1 ? "" : "s"} · {map.ownerCount} owner
        {map.ownerCount === 1 ? "" : "s"} · {map.worldDim.x} × {map.worldDim.z}
        {hotspots.length > 0 && ` · ${hotspots.length} activity hotspots`}
      </p>
      {map.owners.length > 0 && (
        <ul className="map-legend" data-testid="map-owners">
          {map.owners.slice(0, 16).map((o) => (
            <li key={o}>
              <span
                className="eco-swatch"
                style={{ background: map.owner_colors[o], borderColor: map.owner_strokes[o] }}
              />
              <span className="map-owner-name">{o}</span>
            </li>
          ))}
          {map.owners.length > 16 && (
            <li className="map-legend-more">+{map.owners.length - 16} more</li>
          )}
        </ul>
      )}
    </div>
  )
}

export default function MapPage() {
  const [snap, setSnap] = useState<EcoregionSnapshot | null>(null)
  const [world, setWorld] = useState<WorldActivity | null>(null)
  const [map, setMap] = useState<MapPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [hoveredBiome, setHoveredBiome] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const guard = (fn: () => void) => {
      if (!controller.signal.aborted) fn()
    }
    // Three independent planes; a failure in any one degrades that section
    // rather than the page. The shared loading state clears once all settle.
    Promise.allSettled([
      fetchEcoregion(controller.signal).then((d) => guard(() => setSnap(d))),
      fetchWorld(controller.signal).then((d) => guard(() => setWorld(d))),
      fetchMap(controller.signal).then((d) => guard(() => setMap(d))),
    ]).finally(() => guard(() => setLoading(false)))
    return () => controller.abort()
  }, [])

  // Which biomes can actually highlight on the map (have a fetched raster).
  const highlightable = useMemo(
    () => new Set((map?.biomeLayers ?? []).map((b) => b.name)),
    [map],
  )

  const topMatch = snap?.ecoregionMatches[0]
  const worldEmpty = world != null && world.totalEvents === 0

  return (
    <Layout fetchedAtISO={world?.fetchedAtISO}>
      <section className="hero hero-compact">
        <p className="hero-kicker">World map &amp; ecoregion</p>
        <h1 className="hero-title">
          The world, <span className="accent">mapped and classified</span>
        </h1>
        {snap && (
          <p className="hero-pill" data-testid="map-pill">
            <span className="pulse-dot" aria-hidden="true" />
            {topMatch
              ? `Closest to ${topMatch.name} · ${Math.round(snap.classifiedPercent)}% classified`
              : `${Math.round(snap.classifiedPercent)}% of the map is classified`}
            {world && !worldEmpty && ` · ${formatCount(world.totalEvents)} world-mutation events`}
          </p>
        )}
        {!snap && !loading && (
          <p className="hero-pill hero-pill-muted" data-testid="map-error">
            world snapshot unavailable right now
          </p>
        )}
      </section>

      {loading && <Loading label="Reading the world map, biomes, and activity…" />}

      {!loading && (
        <>
          {map ? (
            <section>
              <h2 className="section-title">World map</h2>
              <p className="intro">
                <span>
                  The live world preview, blown up and readable. Every property deed is drawn as a
                  translucent polygon coloured by owner; the ringed dots mark where the bulldozers
                  are busiest. Hover a biome below to light up where it sits.
                </span>
              </p>
              <WorldMap map={map} world={world} hoveredBiome={hoveredBiome} />
            </section>
          ) : (
            <section>
              <h2 className="section-title">World map</h2>
              <p className="empty-note" data-testid="map-unavailable">
                The world preview is unavailable right now.
              </p>
            </section>
          )}

          {snap && (
            <section>
              <h2 className="section-title">Biome &amp; water composition</h2>
              <p className="intro">
                <span>
                  Share of the whole map covered by each biome and by water. Coastal sea and fresh
                  water used to vanish into an unlabelled 61% grey slice — now only genuine mountain
                  and transitional terrain ({Math.round(snap.unclassifiedPercent)}%) is left
                  unclassified.
                </span>
              </p>
              <div className="eco-donut-row">
                <Donut snap={snap} />
                <ul className="eco-legend" data-testid="eco-legend">
                  {snap.biomes
                    .filter((b) => b.percent > 0)
                    .map((b) => {
                      const canHighlight = highlightable.has(b.name)
                      return (
                        <li
                          key={b.name}
                          className={canHighlight ? "eco-legend-hoverable" : undefined}
                          data-testid={`biome-legend-${b.name}`}
                          onMouseEnter={() => canHighlight && setHoveredBiome(b.name)}
                          onMouseLeave={() => setHoveredBiome((h) => (h === b.name ? null : h))}
                          onFocus={() => canHighlight && setHoveredBiome(b.name)}
                          onBlur={() => setHoveredBiome((h) => (h === b.name ? null : h))}
                          tabIndex={canHighlight ? 0 : undefined}
                        >
                          <span className="eco-swatch" style={{ background: b.color }} />
                          <span className="eco-legend-label">{b.display}</span>
                          <span className="eco-legend-pct">{Math.round(b.percent)}%</span>
                        </li>
                      )
                    })}
                  <li>
                    <span className="eco-swatch" style={{ background: UNCLASSIFIED_COLOR }} />
                    <span className="eco-legend-label">Unclassified / mixed terrain</span>
                    <span className="eco-legend-pct">{Math.round(snap.unclassifiedPercent)}%</span>
                  </li>
                </ul>
              </div>
              {highlightable.size > 0 && (
                <p className="hint-line" data-testid="biome-hint">
                  Hover a highlighted biome name to see where it is on the map above.
                </p>
              )}
            </section>
          )}

          {snap && (
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
          )}

          {snap && (
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
          )}

          {world && !worldEmpty && (
            <>
              <section>
                <h2 className="section-title">Mutation timeline</h2>
                <p className="intro">
                  <span>
                    Every construction, road, moved object, explosion, garbage drop, and pollution
                    event the world logs, stacked by category over in-game days.
                  </span>
                </p>
                <MutationTimeline world={world} />
                <TimelineLegend world={world} />
              </section>

              <section>
                <h2 className="section-title">By category</h2>
                <div className="stats">
                  {world.categories.map((c) => (
                    <div className="stat" key={c.key}>
                      <p className="stat-value">{formatCount(c.events)}</p>
                      <p className="stat-label">{c.label}</p>
                      <p className="stat-detail">{formatCount(c.volume)} volume</p>
                    </div>
                  ))}
                </div>
              </section>

              <div className="atlas-columns">
                <section>
                  <h2 className="section-title">Top world-shapers</h2>
                  <RankList
                    rows={world.byCitizen.map(([name, count]) => ({ name, count }))}
                    emptyNote="No citizen activity recorded."
                    testid="shapers"
                  />
                </section>
                <section>
                  <h2 className="section-title">Top polluters</h2>
                  <RankList
                    rows={world.byPolluter.map(([name, count]) => ({ name, count }))}
                    emptyNote="No pollution events recorded."
                    testid="polluters"
                  />
                </section>
              </div>

              <div className="atlas-columns">
                <section>
                  <h2 className="section-title">Most-touched objects</h2>
                  <p className="intro">
                    <span>Ranked by how many times each object was placed, moved, dug, or chopped.</span>
                  </p>
                  <RankList
                    rows={world.byObject.map(([name, count]) => ({ name, count }))}
                    emptyNote="No object activity recorded."
                    prettify
                    testid="objects"
                  />
                </section>
                <section>
                  <h2 className="section-title">Activity hotspots</h2>
                  <p className="intro">
                    <span>The busiest map cells — also ringed on the world map above.</span>
                  </p>
                  <RankList
                    rows={world.hotspots.map((h) => ({ name: `(${h.x}, ${h.z})`, count: h.events }))}
                    emptyNote="No positioned events recorded."
                    testid="hotspots"
                  />
                </section>
              </div>

              {world.warnings.length > 0 && (
                <section>
                  <ul className="explainer" data-testid="world-warnings">
                    {world.warnings.map((w, i) => (
                      <li key={i}>⚠ {w}</li>
                    ))}
                  </ul>
                </section>
              )}
            </>
          )}

          <section className="dir-cards">
            <Link className="dir-card" to="/climate" data-testid="link-climate">
              <h3>Climate →</h3>
              <p>What CO₂, temperature, and sea level are doing to the world these species live in.</p>
            </Link>
            <Link className="dir-card" to="/crafting" data-testid="link-crafting">
              <h3>Crafting atlas →</h3>
              <p>The production side of this activity — what all this digging and chopping becomes.</p>
            </Link>
          </section>
        </>
      )}
    </Layout>
  )
}
