import { useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"
import Layout from "../components/Layout"
import { useJobsData } from "../hooks/useJobsData"
import type { PlayerRow, ProfessionStat, SpecialtyStat } from "../lib/jobsApi"
import {
  fetchProgressionHistory,
  KIND_LABELS,
  type CitizenTrajectory,
  type ProgressionHistory,
} from "../lib/progressionApi"
import { formatCount } from "../lib/format"

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

export default function Jobs() {
  const { data, error, loading } = useJobsData()
  // Progression is a best-effort enrichment — a failure leaves the jobs page
  // exactly as it was before this surface existed, so we swallow errors.
  const [progression, setProgression] = useState<ProgressionHistory | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchProgressionHistory(controller.signal)
      .then(setProgression)
      .catch(() => {
        /* non-fatal: the history lane just doesn't render */
      })
    return () => controller.abort()
  }, [])

  const trajectoryByName = useMemo(() => {
    const map = new Map<string, CitizenTrajectory>()
    for (const c of progression?.citizens ?? []) map.set(c.name, c)
    return map
  }, [progression])

  const hasHistory = (progression?.totalEvents ?? 0) > 0

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
          Who can make what on the Eco server — professions, specialties, and which players
          have which skills learned. "Active" means the player has logged in within the last
          week; "total" counts everyone who's ever touched the skill.
        </p>
      </section>

      {hasHistory && (
        <section className="jobs-history-lane" data-testid="jobs-history-lane">
          <h2 className="section-title">
            Skill history{" "}
            <span className="section-sub">
              ({formatCount(progression!.totalEvents)} recorded events — how these skills were
              earned)
            </span>
          </h2>
          <p className="intro">
            The tables below are the current state. The <Link to="/progression">progression
            history</Link> is how everyone got there — expand a player below for their timeline, or
            open the full view for server-wide trends and trajectories.
          </p>
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
              {data.professions.map((s) => (
                <ProfessionCard key={s.profession} stat={s} />
              ))}
            </ul>
          </section>

          <section>
            <h2 className="section-title">Specialties</h2>
            <ul className="cards">
              {data.specialties.map((s) => (
                <SpecialtyCard key={s.specialty} stat={s} />
              ))}
            </ul>
          </section>

          <section>
            <h2 className="section-title">Players</h2>
            <ul className="cards">
              {data.players.map((p) => (
                <PlayerCard key={p.name} player={p} trajectory={trajectoryByName.get(p.name)} />
              ))}
            </ul>
          </section>
        </>
      )}
    </Layout>
  )
}
