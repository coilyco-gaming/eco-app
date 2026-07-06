import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import Layout from "../components/Layout"
import { fetchCivics, type CivicsReport } from "../lib/civicsApi"
import { formatCount } from "../lib/format"

const TOP_N = 12
const RECENT = 12

type Series = Array<[number, number]>

// Two-line turnout chart: votes cast vs abstentions per in-game day. Same
// unit and scale on both lines (a daily count), so one shared y-axis — never a
// dual axis. Hand-rolled polyline like the trades price chart: no chart lib
// keeps the bundle lean and CSP trivial. Two series → a legend is always
// present, so identity is never colour-alone.
function TurnoutChart({ vote, didntVote }: { vote: Series; didntVote: Series }) {
  const width = 640
  const height = 180
  const pad = 30
  const all = [...vote, ...didntVote]
  if (all.length < 2) {
    return <p className="empty-note">Not enough turnout history to chart yet.</p>
  }
  const days = all.map(([d]) => d)
  const values = all.map(([, v]) => v)
  const minDay = Math.min(...days)
  const maxDay = Math.max(...days)
  const maxVal = Math.max(...values, 1)
  const daySpan = maxDay - minDay || 1

  const x = (d: number) => pad + ((d - minDay) / daySpan) * (width - 2 * pad)
  const y = (v: number) => height - pad - (v / maxVal) * (height - 2 * pad)
  const toLine = (pts: Series) =>
    pts.map(([d, v]) => `${x(d).toFixed(1)},${y(v).toFixed(1)}`).join(" ")

  return (
    <svg
      className="price-chart"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Votes cast vs abstentions by in-game day"
      data-testid="turnout-chart"
    >
      {vote.length >= 2 && (
        <polyline points={toLine(vote)} fill="none" stroke="var(--leaf)" strokeWidth="2" />
      )}
      {didntVote.length >= 2 && (
        <polyline
          points={toLine(didntVote)}
          fill="none"
          stroke="var(--meteor)"
          strokeWidth="2"
          strokeDasharray="5 3"
        />
      )}
      <text x={pad} y={height - 6} className="axis-label">
        day {minDay}
      </text>
      <text x={width - pad} y={height - 6} textAnchor="end" className="axis-label">
        day {maxDay}
      </text>
      <text x={pad} y={16} className="axis-label">
        {formatCount(maxVal)} / day
      </text>
    </svg>
  )
}

interface RankProps {
  rows: Array<[string, number]>
  label: string
}

function RankList({ rows, label }: RankProps) {
  const top = rows.slice(0, TOP_N)
  const max = Math.max(...top.map(([, n]) => n), 1)
  if (top.length === 0) {
    return <p className="empty-note">No {label} recorded.</p>
  }
  return (
    <ul className="rank-rows">
      {top.map(([name, n]) => (
        <li key={name}>
          <div className="rank-row" data-testid="voter-row">
            <span className="rank-name">{name}</span>
            <span className="rank-count">{formatCount(n)}</span>
            <span className="rank-bar" style={{ width: `${(n / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  )
}

export default function Civics() {
  const [report, setReport] = useState<CivicsReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchCivics(controller.signal)
      .then(setReport)
      .catch((err) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err))
      })
    return () => controller.abort()
  }, [])

  const turnoutPct =
    report && report.turnoutRate !== null ? Math.round(report.turnoutRate * 100) : null

  return (
    <Layout>
      <section className="hero hero-compact">
        <p className="hero-kicker">Civics &amp; governance</p>
        <h1 className="hero-title">
          Elections, turnout, and a <span className="accent">changing populace</span>
        </h1>
        <p className="hero-tagline">
          The history and trend of civic life on the server — who ran, who voted, who moved
          in, and where new settlements rose. For the current title chart and active laws, see{" "}
          <Link to="/server">Server</Link>.
        </p>
        {report && report.totalEvents > 0 && (
          <p className="hero-pill" data-testid="civics-pill">
            <span className="pulse-dot" aria-hidden="true" />
            {formatCount(report.totalEvents)} civic events
            {turnoutPct !== null ? ` · ${turnoutPct}% turnout` : ""}
          </p>
        )}
        {!report && error && (
          <p className="hero-pill hero-pill-muted" data-testid="civics-error">
            civics report unavailable right now
          </p>
        )}
      </section>

      {report && report.totalEvents === 0 && (
        <section>
          <p className="empty-note" data-testid="civics-empty">
            No civic events recorded on this server yet. Early in a cycle this is normal —
            elections, citizenships, and settlements show up here as they happen.
          </p>
        </section>
      )}

      {report && report.totalEvents > 0 && (
        <>
          <section className="stats" aria-label="civic snapshot" data-testid="civics-stats">
            <div className="stat">
              <p className="stat-value">{turnoutPct !== null ? `${turnoutPct}%` : "—"}</p>
              <p className="stat-label">Turnout</p>
              <p className="stat-detail">
                {formatCount(report.votesCast)} cast · {formatCount(report.abstentions)} abstained
              </p>
            </div>
            <div className="stat">
              <p className="stat-value">{formatCount(report.electionsStarted)}</p>
              <p className="stat-label">Elections</p>
              <p className="stat-detail">{formatCount(report.electionsWon)} won</p>
            </div>
            <div className="stat">
              <p className="stat-value">
                {report.netCitizens >= 0 ? "+" : ""}
                {formatCount(report.netCitizens)}
              </p>
              <p className="stat-label">Net citizens</p>
              <p className="stat-detail">
                +{formatCount(report.citizensGained)} / -{formatCount(report.citizensLost)}
              </p>
            </div>
            <div className="stat">
              <p className="stat-value">{formatCount(report.residencyMoves)}</p>
              <p className="stat-label">Residency moves</p>
            </div>
            <div className="stat">
              <p className="stat-value">{formatCount(report.settlementsFounded)}</p>
              <p className="stat-label">Settlements</p>
              <p className="stat-detail">{formatCount(report.homesteadsStarted)} homesteads</p>
            </div>
          </section>

          {(report.trend.Vote || report.trend.DidntVote) && (
            <section>
              <h2 className="section-title">Turnout over time</h2>
              <p className="civ-legend" data-testid="turnout-legend">
                <span className="civ-legend-item">
                  <span className="civ-legend-swatch" style={{ background: "var(--leaf)" }} /> votes
                  cast
                </span>
                <span className="civ-legend-item">
                  <span
                    className="civ-legend-swatch civ-legend-swatch-dashed"
                    style={{ color: "var(--meteor)" }}
                  />{" "}
                  abstentions
                </span>
              </p>
              <TurnoutChart
                vote={report.trend.Vote ?? []}
                didntVote={report.trend.DidntVote ?? []}
              />
            </section>
          )}

          {report.recentElections.length > 0 && (
            <section>
              <h2 className="section-title">
                Recent elections{" "}
                <span className="section-sub">(newest {Math.min(RECENT, report.recentElections.length)})</span>
              </h2>
              <table className="ledger-table" data-testid="elections-table">
                <thead>
                  <tr>
                    <th>Day</th>
                    <th>Election</th>
                    <th>Proposed by</th>
                  </tr>
                </thead>
                <tbody>
                  {report.recentElections.slice(0, RECENT).map((e, i) => (
                    <tr key={`${e.day}-${i}`} data-testid="election-row">
                      <td>{e.day}</td>
                      <td>{e.subject || "Election"}</td>
                      <td>{e.proposer || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          <div className="atlas-columns">
            <section>
              <h2 className="section-title">Most-active voters</h2>
              <RankList rows={report.topVoters} label="votes" />
            </section>
            {report.recentSettlements.length > 0 && (
              <section>
                <h2 className="section-title">New settlements &amp; homesteads</h2>
                <ul className="rank-rows" data-testid="settlements-list">
                  {report.recentSettlements.slice(0, TOP_N).map((s, i) => (
                    <li key={`${s.day}-${i}`}>
                      <div className="rank-row" data-testid="settlement-row">
                        <span className="rank-name">
                          {s.subject || (s.kind === "homestead" ? "Homestead" : "Settlement")}
                        </span>
                        <span className="rank-count">
                          {s.founder || "—"} · day {s.day}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>

          {report.recentDemographics.length > 0 && (
            <section>
              <h2 className="section-title">
                Recent arrivals &amp; departures{" "}
                <span className="section-sub">(citizens joining / leaving)</span>
              </h2>
              <table className="ledger-table" data-testid="demographics-table">
                <thead>
                  <tr>
                    <th>Day</th>
                    <th>Citizen</th>
                    <th>Change</th>
                  </tr>
                </thead>
                <tbody>
                  {report.recentDemographics.slice(0, RECENT).map((d, i) => (
                    <tr key={`${d.day}-${i}`} data-testid="demographic-row">
                      <td>{d.day}</td>
                      <td>{d.name || "—"}</td>
                      <td>{d.kind === "joined" ? "🟢 joined" : "⚪ left"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {report.warnings.length > 0 && (
            <section>
              <ul className="warn-list" data-testid="civics-warnings">
                {report.warnings.map((w) => (
                  <li key={w}>⚠ {w}</li>
                ))}
              </ul>
            </section>
          )}

          <section className="dir-cards">
            <Link className="dir-card" to="/server" data-testid="link-server">
              <h3>Server →</h3>
              <p>The live snapshot — elected titles, active laws, and the world at a glance.</p>
            </Link>
          </section>
        </>
      )}
    </Layout>
  )
}
