import { useState } from "react"
import Layout from "../components/Layout"
import { useJobsData } from "../hooks/useJobsData"
import type { PlayerRow, ProfessionStat, SpecialtyStat } from "../lib/jobsApi"

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

function PlayerCard({ player }: { player: PlayerRow }) {
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
    </li>
  )
}

export default function Jobs() {
  const { data, error, loading } = useJobsData()

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
                <PlayerCard key={p.name} player={p} />
              ))}
            </ul>
          </section>
        </>
      )}
    </Layout>
  )
}
