import { useEffect, useMemo, useState } from "react"
import { Link, useParams } from "react-router-dom"
import Layout from "../components/Layout"
import { formatCount, formatFetchedAt, prettifyEcoName } from "../lib/format"
import {
  decodeUserHex,
  fetchUserDossier,
  type UserDossier,
} from "../lib/usersApi"

// A labelled stat tile, mirroring the /map stat grids.
function Stat({ value, label, detail }: { value: string; label: string; detail?: string }) {
  return (
    <div className="stat">
      <p className="stat-value">{value}</p>
      <p className="stat-label">{label}</p>
      {detail && <p className="stat-detail">{detail}</p>}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="section-title">{title}</h2>
      {children}
    </section>
  )
}

// The hidden per-user dossier at /users/<hex> (eco-app#80). <hex> is the base16
// of the username; we decode it, fetch every per-user field the exporters
// carry, and render each surface as its own panel that degrades on its own.
export default function User() {
  const { hex = "" } = useParams()
  const [dossier, setDossier] = useState<UserDossier | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Decode the base16 path segment to the username before any fetch. A
  // malformed segment is a bad link, surfaced distinctly from a fetch failure.
  const decoded = useMemo(() => {
    try {
      return { username: decodeUserHex(hex), badHex: false }
    } catch {
      return { username: "", badHex: true }
    }
  }, [hex])

  useEffect(() => {
    if (decoded.badHex) return
    const controller = new AbortController()
    fetchUserDossier(decoded.username, controller.signal)
      .then(setDossier)
      .catch((err) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err))
      })
    return () => controller.abort()
  }, [decoded])

  if (decoded.badHex) {
    return (
      <Layout>
        <section className="hero hero-compact">
          <p className="hero-kicker">User dossier</p>
          <h1 className="hero-title">Not a valid user link</h1>
          <p className="empty-note" data-testid="user-bad-hex">
            The <code>/users/&lt;hex&gt;</code> segment must be the base16 of a username.
            <br />
            <Link to="/users">Browse every user →</Link>
          </p>
        </section>
      </Layout>
    )
  }

  const username = decoded.username

  return (
    <Layout fetchedAtISO={dossier?.fetchedAtISO}>
      <section className="hero hero-compact">
        <p className="hero-kicker">User dossier</p>
        <h1 className="hero-title">
          <span className="accent" data-testid="user-name">
            {username}
          </span>
        </h1>
        {dossier?.jobs && (
          <p className="hero-pill" data-testid="user-pill">
            <span className="pulse-dot" aria-hidden="true" />
            {dossier.jobs.active ? "active" : "inactive"}
            {dossier.jobs.lastSeenISO
              ? ` · last seen ${formatFetchedAt(dossier.jobs.lastSeenISO)}`
              : " · never logged in"}
          </p>
        )}
        {!dossier && error && (
          <p className="hero-pill hero-pill-muted" data-testid="user-error">
            dossier unavailable right now
          </p>
        )}
        <p className="redaction-note">
          Every field the server exports about one player, pivoted into one place. Hidden by design
          — no nav link, no password. <Link to="/users">All users →</Link>
        </p>
      </section>

      {dossier && !dossier.found && (
        <section>
          <p className="empty-note" data-testid="user-not-found">
            No exported data mentions <strong>{username}</strong> yet. They may not have played, or
            the exporters that would carry their activity are unavailable.
          </p>
        </section>
      )}

      {dossier?.jobs && (
        <Section title="Skills & jobs">
          {dossier.jobs.specialties.length === 0 ? (
            <p className="empty-note">No learned specialties.</p>
          ) : (
            <table className="ledger-table" data-testid="user-specialties">
              <thead>
                <tr>
                  <th>Specialty</th>
                  <th>Level</th>
                  <th>Active</th>
                </tr>
              </thead>
              <tbody>
                {dossier.jobs.specialties.map((s) => (
                  <tr key={s.specialty}>
                    <td>{s.specialty}</td>
                    <td>{s.level}</td>
                    <td>{s.active ? "yes" : "no"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Section>
      )}

      {dossier?.trades && (
        <Section title="Trades">
          <div className="stats">
            <Stat value={formatCount(dossier.trades.currencySpent)} label="Spent as buyer" />
            <Stat value={formatCount(dossier.trades.currencyEarned)} label="Earned as seller" />
            <Stat value={formatCount(dossier.trades.trades.length)} label="Trades on record" />
          </div>
          {dossier.trades.trades.length > 0 && (
            <table className="ledger-table" data-testid="user-trades">
              <thead>
                <tr>
                  <th>Day</th>
                  <th>Item</th>
                  <th>Role</th>
                  <th>Counterparty</th>
                  <th>Amount</th>
                </tr>
              </thead>
              <tbody>
                {dossier.trades.trades.slice(0, 100).map((t, i) => {
                  const role = t.buyer === username ? "bought" : "sold"
                  const counterparty = t.buyer === username ? t.seller : t.buyer
                  return (
                    <tr key={`${t.item}-${i}`} data-testid="user-trade-row">
                      <td>{t.day ?? "—"}</td>
                      <td>{t.item ? prettifyEcoName(t.item) : "—"}</td>
                      <td>{role}</td>
                      <td>{counterparty}</td>
                      <td>
                        {t.currencyAmount != null
                          ? `${formatCount(t.currencyAmount)} ${t.currency ?? ""}`
                          : "—"}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </Section>
      )}

      {dossier?.currency && (
        <Section title="Currency holdings">
          <table className="ledger-table" data-testid="user-holdings">
            <thead>
              <tr>
                <th>Currency</th>
                <th>Balance</th>
                <th>Account</th>
              </tr>
            </thead>
            <tbody>
              {dossier.currency.holdings.map((h) => (
                <tr key={`${h.currency}-${h.account}`}>
                  <td>{h.currency}</td>
                  <td>{formatCount(h.balance)}</td>
                  <td>{h.account}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}

      {(dossier?.crafting || dossier?.world) && (
        <Section title="Production & world">
          <div className="stats">
            {dossier.crafting && (
              <Stat value={formatCount(dossier.crafting.events)} label="Items crafted" />
            )}
            {dossier.world && (
              <>
                <Stat
                  value={formatCount(dossier.world.shaperEvents)}
                  label="World-shaping events"
                />
                <Stat
                  value={formatCount(dossier.world.pollutionEvents)}
                  label="Pollution events"
                />
              </>
            )}
          </div>
        </Section>
      )}

      {dossier?.civics && (
        <Section title="Civics">
          <div className="stats">
            <Stat value={formatCount(dossier.civics.votesCast)} label="Votes cast" />
            <Stat
              value={formatCount(dossier.civics.elections.length)}
              label="Elections proposed / won"
            />
            <Stat
              value={formatCount(dossier.civics.settlements.length)}
              label="Settlements founded"
            />
          </div>
          {(dossier.civics.elections.length > 0 || dossier.civics.settlements.length > 0) && (
            <ul className="warn-list" data-testid="user-civics-events">
              {dossier.civics.elections.map((e, i) => (
                <li key={`el-${i}`}>
                  Day {e.day}: {e.role} <strong>{e.subject}</strong>
                </li>
              ))}
              {dossier.civics.settlements.map((s, i) => (
                <li key={`st-${i}`}>
                  Day {s.day}: founded {s.kind} <strong>{s.subject}</strong>
                </li>
              ))}
            </ul>
          )}
        </Section>
      )}

      {dossier?.progression && (
        <Section title="Progression">
          <div className="stats">
            <Stat value={formatCount(dossier.progression.levelUpCount)} label="Level-ups" />
            {dossier.progression.trajectory?.characterLevel != null && (
              <Stat
                value={formatCount(dossier.progression.trajectory.characterLevel)}
                label="Character level"
              />
            )}
            {dossier.progression.trajectory && (
              <Stat
                value={formatCount(dossier.progression.trajectory.eventCount ?? 0)}
                label="Progression events"
              />
            )}
          </div>
          {dossier.progression.trajectory?.professions &&
            dossier.progression.trajectory.professions.length > 0 && (
              <p className="intro" data-testid="user-professions">
                <span>
                  Professions:{" "}
                  {dossier.progression.trajectory.professions.map((p) => p.pretty).join(", ")}
                </span>
              </p>
            )}
          {dossier.progression.trajectory?.timeline &&
            dossier.progression.trajectory.timeline.length > 0 && (
              <table className="ledger-table" data-testid="user-timeline">
                <thead>
                  <tr>
                    <th>Day</th>
                    <th>Event</th>
                    <th>Skill</th>
                    <th>Level</th>
                  </tr>
                </thead>
                <tbody>
                  {dossier.progression.trajectory.timeline.map((ev, i) => (
                    <tr key={`tl-${i}`}>
                      <td>{ev.day}</td>
                      <td>{ev.kind}</td>
                      <td>{ev.pretty}</td>
                      <td>{ev.level ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
        </Section>
      )}

      {dossier && dossier.warnings.length > 0 && (
        <section>
          <ul className="warn-list" data-testid="user-warnings">
            {dossier.warnings.map((w) => (
              <li key={w}>⚠ {w}</li>
            ))}
          </ul>
        </section>
      )}
    </Layout>
  )
}
