import { useEffect, useMemo, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import Layout from "../components/Layout"
import {
  fetchProgressionHistory,
  KIND_LABELS,
  TREND_ORDER,
  type CitizenTrajectory,
  type ProgressionHistory,
} from "../lib/progressionApi"
import { formatCount, prettifyEcoName } from "../lib/format"

const TOP_N = 15
const CITIZEN_CARDS = 40

// One small-multiple sparkline of a single trend series (events of one kind per
// in-game day). Small multiples — one single-hue chart per kind — deliberately
// sidestep the multi-series categorical-color problem: every panel reads on the
// same --leaf hue, and its title names the single series (no legend box needed).
function TrendSparkline({
  label,
  points,
}: {
  label: string
  points: Array<[number, number]>
}) {
  const width = 300
  const height = 96
  const pad = 16
  const total = points.reduce((sum, [, c]) => sum + c, 0)

  let body
  if (points.length < 2) {
    // A single day (or none) can't draw a line; show the headline count instead.
    body = (
      <p className="prog-trend-single" data-testid="trend-single">
        {formatCount(total)} total{points.length === 1 ? ` · day ${points[0][0]}` : ""}
      </p>
    )
  } else {
    const days = points.map(([d]) => d)
    const counts = points.map(([, c]) => c)
    const minDay = Math.min(...days)
    const maxDay = Math.max(...days)
    const maxCount = Math.max(...counts)
    const daySpan = maxDay - minDay || 1
    const countSpan = maxCount || 1
    const x = (d: number) => pad + ((d - minDay) / daySpan) * (width - 2 * pad)
    const y = (c: number) => height - pad - (c / countSpan) * (height - 2 * pad)
    const line = points.map(([d, c]) => `${x(d).toFixed(1)},${y(c).toFixed(1)}`).join(" ")
    const area = `${x(minDay).toFixed(1)},${(height - pad).toFixed(1)} ${line} ${x(
      maxDay,
    ).toFixed(1)},${(height - pad).toFixed(1)}`
    body = (
      <svg
        className="prog-trend-chart"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`${KIND_LABELS[label] ?? label} per in-game day`}
        data-testid="trend-chart"
      >
        <polygon points={area} fill="var(--leaf-wash)" stroke="none" />
        <polyline points={line} fill="none" stroke="var(--leaf)" strokeWidth="2" />
        <text x={pad} y={height - 4} className="axis-label">
          day {minDay}
        </text>
        <text x={width - pad} y={height - 4} textAnchor="end" className="axis-label">
          day {maxDay}
        </text>
        <text x={pad} y={14} className="axis-label">
          peak {formatCount(maxCount)}
        </text>
      </svg>
    )
  }

  return (
    <div className="prog-trend" data-testid="trend-panel">
      <div className="prog-trend-title">
        {KIND_LABELS[label] ?? label}
        <span className="prog-trend-total">{formatCount(total)}</span>
      </div>
      {body}
    </div>
  )
}

// Ranked bar list of [name, count] pairs. `pretty` prettifies Eco skill ids;
// citizen-name lists (already resolved server-side) pass pretty={false}.
function RankList({
  rows,
  emptyNote,
  pretty = true,
}: {
  rows: Array<[string, number]>
  emptyNote: string
  pretty?: boolean
}) {
  const top = rows.slice(0, TOP_N)
  const max = Math.max(...top.map(([, c]) => c), 1)
  if (top.length === 0) {
    return <p className="empty-note">{emptyNote}</p>
  }
  return (
    <ul className="rank-rows">
      {top.map(([name, count]) => (
        <li key={name}>
          <div className="rank-row" data-testid="rank-row">
            <span className="rank-name">{pretty ? prettifyEcoName(name) : name}</span>
            <span className="rank-count">{formatCount(count)}</span>
            <span className="rank-bar" style={{ width: `${(count / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  )
}

// One citizen's trajectory: current professions + held specialties, with an
// expandable event timeline (how they got there — the history lane's core).
function TrajectoryCard({ citizen }: { citizen: CitizenTrajectory }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="card" data-testid="trajectory-card">
      <button
        className="prof-btn"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span>{citizen.name}</span>
        <span className="count">
          {citizen.characterLevel !== null ? `lvl ${Math.round(citizen.characterLevel)} · ` : ""}
          {formatCount(citizen.levelUpCount)} level-ups
        </span>
      </button>
      {citizen.professions.length > 0 && (
        <p className="kicker">{citizen.professions.map((p) => p.pretty).join(", ")}</p>
      )}
      {citizen.specialties.length > 0 && (
        <ul className="rows">
          {citizen.specialties.map((s) => (
            <li key={s.name}>
              <span>{s.pretty}</span>
              {s.level !== null && <span className="lvl">lvl {Math.round(s.level)}</span>}
            </li>
          ))}
        </ul>
      )}
      {open && (
        <div className="detail">
          {citizen.timeline.length > 0 ? (
            <ul className="prog-timeline" data-testid="trajectory-timeline">
              {citizen.timeline.map((ev, i) => (
                <li key={`${ev.time}-${i}`}>
                  <span className="prog-day">day {ev.day}</span>
                  <span className="prog-what">
                    {KIND_LABELS[ev.kind] ?? ev.kind}
                    {ev.skill ? `: ${ev.pretty}` : ""}
                    {ev.level !== null ? ` (lvl ${Math.round(ev.level)})` : ""}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty-note">No recorded events.</p>
          )}
        </div>
      )}
    </li>
  )
}

function matchesCitizen(c: CitizenTrajectory, needle: string): boolean {
  if (!needle) return true
  const hay = [c.name, ...c.professions.map((p) => p.pretty), ...c.specialties.map((s) => s.pretty)]
    .join(" ")
    .toLowerCase()
  return hay.includes(needle)
}

export default function Progression() {
  const [history, setHistory] = useState<ProgressionHistory | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [params, setParams] = useSearchParams()
  const q = params.get("q") ?? ""

  useEffect(() => {
    const controller = new AbortController()
    fetchProgressionHistory(controller.signal)
      .then(setHistory)
      .catch((err) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err))
      })
    return () => controller.abort()
  }, [])

  const setQuery = (value: string) => {
    setParams(value ? { q: value } : {}, { replace: false })
  }

  const trendPanels = useMemo(() => {
    if (!history) return []
    return TREND_ORDER.filter((kind) => (history.trends[kind]?.length ?? 0) > 0).map((kind) => ({
      kind,
      points: history.trends[kind],
    }))
  }, [history])

  const needle = q.trim().toLowerCase()
  const visibleCitizens = useMemo(
    () =>
      history
        ? history.citizens.filter((c) => matchesCitizen(c, needle)).slice(0, CITIZEN_CARDS)
        : [],
    [history, needle],
  )

  return (
    <Layout>
      <section className="hero hero-compact">
        <p className="hero-kicker">Progression history</p>
        <h1 className="hero-title">
          How the world <span className="accent">learned</span>
        </h1>
        {history && (
          <p className="hero-pill" data-testid="progression-pill">
            <span className="pulse-dot" aria-hidden="true" />
            {formatCount(history.totalEvents)} skill events across{" "}
            {formatCount(history.citizens.length)} citizens
          </p>
        )}
        {!history && error && (
          <p className="hero-pill hero-pill-muted" data-testid="progression-error">
            progression history unavailable right now
          </p>
        )}
      </section>

      {history && history.totalEvents === 0 && (
        <section>
          <p className="empty-note" data-testid="progression-empty">
            No progression events recorded on this server yet. Early in a cycle this is normal —
            check back after a few days of play.
          </p>
        </section>
      )}

      {history && history.totalEvents > 0 && (
        <>
          {trendPanels.length > 0 && (
            <section>
              <h2 className="section-title">
                Progression trends <span className="section-sub">(events per in-game day)</span>
              </h2>
              <div className="prog-trend-grid" data-testid="trend-grid">
                {trendPanels.map(({ kind, points }) => (
                  <TrendSparkline key={kind} label={kind} points={points} />
                ))}
              </div>
            </section>
          )}

          <div className="atlas-columns">
            <section>
              <h2 className="section-title">Most-gained specialties</h2>
              <RankList rows={history.bySpecialty} emptyNote="No specialties gained yet." />
            </section>
            <section>
              <h2 className="section-title">Busiest levelers</h2>
              <RankList
                rows={history.topLevelers}
                emptyNote="No level-ups recorded yet."
                pretty={false}
              />
            </section>
          </div>

          {history.classCompletions.length > 0 && (
            <section>
              <h2 className="section-title">Classes completed</h2>
              <RankList rows={history.classCompletions} emptyNote="No classes completed yet." />
            </section>
          )}

          <section className="filter-row">
            <input
              className="filter-input"
              type="search"
              placeholder="Filter citizens by name, profession, or specialty… (deep-linkable as ?q=)"
              value={q}
              onChange={(e) => setQuery(e.target.value)}
              data-testid="progression-filter"
            />
            {q && (
              <button className="button" onClick={() => setQuery("")}>
                Clear
              </button>
            )}
          </section>

          <section>
            <h2 className="section-title">
              Skill trajectories{" "}
              <span className="section-sub">
                ({visibleCitizens.length}
                {history.citizens.length > visibleCitizens.length
                  ? ` of ${formatCount(history.citizens.length)}`
                  : ""}
                {" — expand for the timeline"})
              </span>
            </h2>
            {visibleCitizens.length === 0 ? (
              <p className="empty-note">No citizens match.</p>
            ) : (
              <ul className="cards" data-testid="trajectory-cards">
                {visibleCitizens.map((c) => (
                  <TrajectoryCard key={c.name} citizen={c} />
                ))}
              </ul>
            )}
          </section>

          {history.warnings.length > 0 && (
            <section>
              <ul className="warn-list" data-testid="progression-warnings">
                {history.warnings.map((w) => (
                  <li key={w}>⚠ {w}</li>
                ))}
              </ul>
            </section>
          )}

          <section className="dir-cards">
            <Link className="dir-card" to="/jobs" data-testid="link-jobs">
              <h3>Jobs →</h3>
              <p>The current-state view — who holds which specialty and profession right now.</p>
            </Link>
            <Link className="dir-card" to="/crafting" data-testid="link-crafting">
              <h3>Crafting atlas →</h3>
              <p>Skill provenance — what these skills got used to make, where, and from what.</p>
            </Link>
          </section>
        </>
      )}
    </Layout>
  )
}
