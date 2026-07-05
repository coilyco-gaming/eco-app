import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import Layout from "../components/Layout"
import { fetchEconomy, type EconomySnapshot } from "../lib/econApi"
import { formatCount } from "../lib/format"

interface Stat {
  label: string
  value: string
  detail?: string
}

function pct(v: number): string {
  return `${Math.round(v * 1000) / 10}%`
}

export default function Economy() {
  const [snapshot, setSnapshot] = useState<EconomySnapshot | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchEconomy(controller.signal)
      .then(setSnapshot)
      .catch((err) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err))
      })
    return () => controller.abort()
  }, [])

  const k = snapshot?.kpis

  const trade: Stat[] = k
    ? [
        { label: "Trades / day", value: formatCount(k.trades_per_day) },
        {
          label: "Trades all cycle",
          value: formatCount(k.trades_total),
          detail: k.trades_wow_pct ? `${pct(k.trades_wow_pct / 100)} week over week` : undefined,
        },
        {
          label: "Contracts",
          value: formatCount(k.contracts_posted),
          detail: `${formatCount(k.contracts_completed)} completed · ${formatCount(k.contracts_failed)} failed`,
        },
        {
          label: "Loans",
          value: formatCount(k.loans_accepted),
          detail: `${pct(k.loan_default_rate)} default rate`,
        },
      ]
    : []

  const treasury: Stat[] = k
    ? [
        { label: "Wages paid", value: formatCount(k.wages_total) },
        { label: "Taxes paid", value: formatCount(k.taxes_paid) },
        { label: "Government funds", value: formatCount(k.govt_funds) },
        { label: "Total culture", value: formatCount(k.total_culture) },
      ]
    : []

  return (
    <Layout>
      <section className="hero hero-compact">
        <p className="hero-kicker">Economy</p>
        <h1 className="hero-title">
          The <span className="accent">market pulse</span> of the world
        </h1>
        {snapshot && (
          <p
            className={`hero-pill${snapshot.health === "healthy" ? "" : " hero-pill-warn"}`}
            data-testid="health-pill"
          >
            <span className="pulse-dot" aria-hidden="true" />
            {snapshot.narrative}
          </p>
        )}
        {!snapshot && error && (
          <p className="hero-pill hero-pill-muted" data-testid="econ-error">
            economy snapshot unavailable right now
          </p>
        )}
      </section>

      {snapshot && (
        <>
          <section>
            <h2 className="section-title">Trade</h2>
            <div className="stats">
              {trade.map((s) => (
                <div className="stat" key={s.label}>
                  <p className="stat-value">{s.value}</p>
                  <p className="stat-label">{s.label}</p>
                  {s.detail && <p className="stat-detail">{s.detail}</p>}
                </div>
              ))}
            </div>
          </section>

          <section>
            <h2 className="section-title">Treasury & culture</h2>
            <div className="stats">
              {treasury.map((s) => (
                <div className="stat" key={s.label}>
                  <p className="stat-value">{s.value}</p>
                  <p className="stat-label">{s.label}</p>
                  {s.detail && <p className="stat-detail">{s.detail}</p>}
                </div>
              ))}
            </div>
          </section>

          <section className="dir-cards">
            <Link className="dir-card" to="/trades" data-testid="link-trades">
              <h3>Trades ledger →</h3>
              <p>
                The row-level view behind those {formatCount(snapshot.kpis.trades_total)} trades —
                who sold what to whom, and price over time.
              </p>
            </Link>
            <Link className="dir-card" to="/crafting" data-testid="link-crafting">
              <h3>Crafting atlas →</h3>
              <p>
                The production side of those {formatCount(snapshot.kpis.trades_total)} trades —
                what's being made, where, and from what.
              </p>
            </Link>
          </section>
        </>
      )}
    </Layout>
  )
}
