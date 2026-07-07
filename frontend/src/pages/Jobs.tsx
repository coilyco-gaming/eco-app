import { useEffect, useMemo, useState } from "react"
import Layout from "../components/Layout"
import { useJobsData } from "../hooks/useJobsData"
import type { PlayerRow, ProfessionStat, SpecialtyStat } from "../lib/jobsApi"
import {
  fetchProgressionHistory,
  KIND_LABELS,
  TREND_ORDER,
  type CitizenTrajectory,
  type ProgressionHistory,
} from "../lib/progressionApi"
import { formatCount, prettifyEcoName } from "../lib/format"

// Survivalist and Self Improvement are the universal starter skills — every
// citizen has them, so they carry no signal and only clutter the roster
// (eco-app#94). We filter them out of every jobs surface (professions,
// specialties, per-player skill lists, and the progression rank lists) in one
// place here. Matching on the prettified, whitespace-collapsed name catches
// both the jobs API's display names ("Self Improvement") and the progression
// endpoint's raw Eco ids ("SelfImprovement", "SurvivalistSkill").
const UNIVERSAL_SKILLS = new Set(["self improvement", "survivalist"])

function isUniversalSkill(name: string): boolean {
  const norm = prettifyEcoName(name)
    .toLowerCase()
    .replace(/\bskill\b/g, "")
    .replace(/\s+/g, " ")
    .trim()
  return UNIVERSAL_SKILLS.has(norm)
}

function ProfessionCard({ stat }: { stat: ProfessionStat }) {
  const [open, setOpen] = useState(false)
  return (
    <li className={`card card-tight${stat.total === 0 ? " dim" : ""}`}>
      <button className="prof-btn" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <span>{stat.profession}</span>
        <span className="count">
          ( {stat.active} / {stat.total} )
        </span>
      </button>
      {open && (
        <div className="detail">
          {stat.players.length > 0 ? (
            <ul className="rows">
              {stat.players.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          ) : (
            <p className="empty-note">No players with specialties in this profession.</p>
          )}
        </div>
      )}
    </li>
  )
}

function SpecialtyCard({ stat }: { stat: SpecialtyStat }) {
  return (
    <li className={`card${stat.active === 0 ? " dim" : ""}`}>
      <h3 className="card-title">
        {stat.specialty}
        <span className="count">
          ( {stat.active} / {stat.total} )
        </span>
      </h3>
      <p className="kicker">{stat.profession}</p>
      <ul className="rows">
        {stat.holders.map((h) => (
          <li key={h.player} className={h.active ? undefined : "faded"}>
            <span>{h.player}</span>
            <span className="lvl">lvl {h.level}</span>
          </li>
        ))}
      </ul>
    </li>
  )
}

// A player card, enriched with a "how they got here" history lane when the
// progression surface has a matching trajectory (eco-app#64). The current-state
// specialties come from the jobs API; the expandable timeline is the history.
function PlayerCard({
  player,
  trajectory,
}: {
  player: PlayerRow
  trajectory?: CitizenTrajectory
}) {
  const [open, setOpen] = useState(false)
  return (
    <li className={`card${player.active ? "" : " dim"}`}>
      <h3 className="card-title">
        {player.name}
        {player.active ? (
          <span className="pill pill-active">active</span>
        ) : (
          <span className="pill pill-inactive">inactive</span>
        )}
      </h3>
      <ul className="rows">
        {player.specialties.map((s) => (
          <li key={s.specialty}>
            <span>{s.specialty}</span>
            <span className="lvl">lvl {s.level}</span>
          </li>
        ))}
      </ul>
      {trajectory && trajectory.timeline.length > 0 && (
        <>
          <button
            className="prof-btn prof-btn-sub"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            data-testid="player-history-toggle"
          >
            <span>How they got here</span>
            <span className="count">{formatCount(trajectory.levelUpCount)} level-ups</span>
          </button>
          {open && (
            <ul className="prog-timeline" data-testid="player-history">
              {trajectory.timeline.map((ev, i) => (
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
          )}
        </>
      )}
    </li>
  )
}

// One small-multiple sparkline of a single progression trend series (events of
// one kind per in-game day). Small multiples — one single-hue chart per kind —
// deliberately sidestep the multi-series categorical-color problem: every panel
// reads on the same --leaf hue, and its title names the single series (no legend
// box needed). Folded into /jobs from the former /progression page (eco-app#90).
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
  const top = rows.slice(0, 15)
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

export default function Jobs() {
  const { data, error, loading } = useJobsData()
  // Progression is the temporal layer of this page (eco-app#90): the current
  // roster shows who does what now, progression shows how they got there. It is
  // a best-effort enrichment — a failure leaves the current-state tables exactly
  // as they were before this surface existed, so we swallow errors.
  const [progression, setProgression] = useState<ProgressionHistory | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchProgressionHistory(controller.signal)
      .then(setProgression)
      .catch(() => {
        /* non-fatal: the trajectory layer just doesn't render */
      })
    return () => controller.abort()
  }, [])

  const trajectoryByName = useMemo(() => {
    const map = new Map<string, CitizenTrajectory>()
    for (const c of progression?.citizens ?? []) map.set(c.name, c)
    return map
  }, [progression])

  const trendPanels = useMemo(() => {
    if (!progression) return []
    return TREND_ORDER.filter((kind) => (progression.trends[kind]?.length ?? 0) > 0).map(
      (kind) => ({ kind, points: progression.trends[kind] }),
    )
  }, [progression])

  const hasHistory = (progression?.totalEvents ?? 0) > 0

  // Drop the universal starter skills from every current-state surface
  // (eco-app#94). Professions and specialties filter by name; players keep
  // their card but shed the two universal rows.
  const professions = useMemo(
    () => (data?.professions ?? []).filter((s) => !isUniversalSkill(s.profession)),
    [data],
  )
  const specialties = useMemo(
    () => (data?.specialties ?? []).filter((s) => !isUniversalSkill(s.specialty)),
    [data],
  )
  const players = useMemo(
    () =>
      (data?.players ?? []).map((p) => ({
        ...p,
        specialties: p.specialties.filter((s) => !isUniversalSkill(s.specialty)),
      })),
    [data],
  )

  // Same exclusion for the progression rank lists (name-keyed leaderboards).
  const dropUniversal = (rows: Array<[string, number]>) =>
    rows.filter(([name]) => !isUniversalSkill(name))

  return (
    <Layout>
      {data?.mockData && (
        <div className="mock-banner" data-testid="mock-banner">
          ⚠️ MOCK DATA — every player, skill, and count on this page is fabricated. Set the{" "}
          <code>UPSTREAM_URL</code> env var on the service to pull real data. ⚠️
        </div>
      )}

      <section className="intro">
        <p>
          Who does what on the Eco server and how they got there — the history up top, the current
          roster below. "Active" means logged in within the last week.
        </p>
      </section>

      {/* The server-wide trajectory layer: how the current roster below formed.
          Moved above the current-state tables so the history reads first
          (eco-app#94); folded in from the former /progression page (eco-app#90). */}
      {hasHistory && (
        <section className="jobs-progression" data-testid="jobs-progression">
          <h2 className="section-title">
            How the world got here{" "}
            <span className="section-sub">
              ({formatCount(progression!.totalEvents)} recorded skill events —{" "}
              {formatCount(progression!.citizens.length)} citizens)
            </span>
          </h2>

          {trendPanels.length > 0 && (
            <div className="prog-trend-grid" data-testid="trend-grid">
              {trendPanels.map(({ kind, points }) => (
                <TrendSparkline key={kind} label={kind} points={points} />
              ))}
            </div>
          )}

          <div className="atlas-columns">
            <div>
              <h3 className="subsection-title">Most-gained specialties</h3>
              <RankList
                rows={dropUniversal(progression!.bySpecialty)}
                emptyNote="No specialties gained yet."
              />
            </div>
            <div>
              <h3 className="subsection-title">Busiest levelers</h3>
              <RankList
                rows={progression!.topLevelers}
                emptyNote="No level-ups recorded yet."
                pretty={false}
              />
            </div>
          </div>

          {dropUniversal(progression!.classCompletions).length > 0 && (
            <>
              <h3 className="subsection-title">Classes completed</h3>
              <RankList
                rows={dropUniversal(progression!.classCompletions)}
                emptyNote="No classes completed yet."
              />
            </>
          )}

          {progression!.warnings.length > 0 && (
            <ul className="warn-list" data-testid="progression-warnings">
              {progression!.warnings.map((w) => (
                <li key={w}>⚠ {w}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      {loading && (
        <p className="loading" data-testid="loading">
          tallying the workshops…
        </p>
      )}

      {error && !data && (
        <p className="loading" data-testid="jobs-error">
          jobs data unavailable right now — the world spins on without us for a moment
        </p>
      )}

      {data && (
        <>
          <section>
            <h2 className="section-title">Professions</h2>
            <ul className="cards">
              {professions.map((s) => (
                <ProfessionCard key={s.profession} stat={s} />
              ))}
            </ul>
          </section>

          <section>
            <h2 className="section-title">Specialties</h2>
            <ul className="cards">
              {specialties.map((s) => (
                <SpecialtyCard key={s.specialty} stat={s} />
              ))}
            </ul>
          </section>

          <section>
            <h2 className="section-title">
              Players{" "}
              {hasHistory && (
                <span className="section-sub">(expand a player for their skill timeline)</span>
              )}
            </h2>
            <ul className="cards">
              {players.map((p) => (
                <PlayerCard key={p.name} player={p} trajectory={trajectoryByName.get(p.name)} />
              ))}
            </ul>
          </section>
        </>
      )}
    </Layout>
  )
}
