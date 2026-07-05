import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import Layout from "../components/Layout"
import { formatCount, prettifyEcoName } from "../lib/format"
import { type WorldActivity, fetchWorld } from "../lib/worldApi"

// Fixed categorical hues, assigned by category identity (never by rank), from
// the dataviz skill's validated theme (dark-mode slots 1-7). The stack ships a
// legend, a 2px surface gap between segments, and per-segment hover labels, so
// identity is never colour-alone — the secondary encoding the CVD floor needs.
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

// Stacked bar of world-mutation events per in-game day, one segment per
// category. No chart lib — a static SVG keeps the bundle lean and CSP trivial,
// matching the sibling /trades and /trade sparklines. One axis (event count);
// day count on x. Segments stack in the stable CATEGORY_ORDER so colour follows
// the entity across servers.
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

  // One slot per day; the bar fills 70% of the slot with a gap either side.
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
      {/* baseline + max gridline, recessive */}
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
              // 2px surface gap between stacked segments.
              const segH = Math.max(0, h - 2)
              const y = cursor - h
              cursor -= h
              return (
                <rect
                  key={k}
                  x={x}
                  y={y}
                  width={barW}
                  height={segH}
                  rx={1}
                  fill={catColor(k)}
                >
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

// Legend — always present for the multi-series stack, so identity is never
// colour-alone. Swatch + label + the category's total event count.
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

// Ranked bar list, mirroring the /crafting rank tables. `prettify` prettifies
// Eco item ids for the objects board; citizen/hotspot rows pass through verbatim.
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

export default function World() {
  const [world, setWorld] = useState<WorldActivity | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchWorld(controller.signal)
      .then(setWorld)
      .catch((err) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err))
      })
    return () => controller.abort()
  }, [])

  const empty = world != null && world.totalEvents === 0

  return (
    <Layout fetchedAtISO={world?.fetchedAtISO}>
      <section className="hero hero-compact">
        <p className="hero-kicker">World &amp; industry</p>
        <h1 className="hero-title">
          What players are <span className="accent">doing to the world</span>
        </h1>
        {world && !empty && (
          <p className="hero-pill" data-testid="world-pill">
            <span className="pulse-dot" aria-hidden="true" />
            {formatCount(world.totalEvents)} world-mutation events ·{" "}
            {world.categories
              .slice(0, 4)
              .map((c) => `${formatCount(c.events)} ${c.label.toLowerCase()}`)
              .join(" · ")}
          </p>
        )}
        {world && empty && (
          <p className="hero-pill hero-pill-muted" data-testid="world-empty">
            no world-mutation events recorded yet
          </p>
        )}
        {!world && error && (
          <p className="hero-pill hero-pill-muted" data-testid="world-error">
            world activity unavailable right now
          </p>
        )}
      </section>

      {world && !empty && (
        <>
          <section>
            <h2 className="section-title">Mutation timeline</h2>
            <p className="intro">
              <span>
                Every construction, road, moved object, explosion, garbage drop, and pollution
                event the world logs, stacked by category over in-game days — the physical story
                of the settlement taking shape.
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
              <RankList
                rows={world.byObject.map(([name, count]) => ({ name, count }))}
                emptyNote="No object activity recorded."
                prettify
                testid="objects"
              />
            </section>
            <section>
              <h2 className="section-title">Activity hotspots</h2>
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

          <section className="dir-cards">
            <Link className="dir-card" to="/climate" data-testid="link-climate">
              <h3>Climate →</h3>
              <p>Where the pollution goes — CO₂, temperature, sea level, and what the air is doing.</p>
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
