import { useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"
import Layout from "../components/Layout"
import {
  fetchEconomy,
  fetchMoney,
  type CurrencyView,
  type EconomySnapshot,
  type MoneyHolders,
  type MoneySnapshot,
} from "../lib/econApi"
import { formatCount } from "../lib/format"

interface Stat {
  label: string
  value: string
  detail?: string
}

function pct(v: number): string {
  return `${Math.round(v * 1000) / 10}%`
}

// Money values carry fractional cents server-side; the headline reads cleaner
// rounded to whole units, so reuse formatCount and suffix the default currency
// symbol nowhere — Eco currencies are named, not glyphed.
function money(n: number): string {
  return formatCount(n)
}

// In-game series time is raw seconds; a game "day" is 86400s (see currency.py
// _series). Whole-day labels keep the axis legible.
function toDay(t: number): number {
  return Math.round(t / 86400)
}

// A compact inline-SVG trend line — one or two series over in-game days. No
// chart lib keeps the bundle lean and the CSP trivial, matching the /trade and
// /progression sparklines. Colour is never the only channel (dataviz
// non-negotiable): each series is named in the legend with its own glyph.
interface TrendSeries {
  points: Array<[number, number]>
  color: string
  label: string
  glyph: string
}

function TrendChart({ series, ariaLabel }: { series: TrendSeries[]; ariaLabel: string }) {
  const width = 640
  const height = 180
  const pad = 32
  const drawable = series.filter((s) => s.points.length >= 2)
  if (drawable.length === 0) {
    return (
      <p className="empty-note" data-testid="trend-empty">
        Not enough history yet to chart the trend — this fills in as the cycle runs.
      </p>
    )
  }
  const allDays = drawable.flatMap((s) => s.points.map(([t]) => toDay(t)))
  const allVals = drawable.flatMap((s) => s.points.map(([, v]) => v))
  const minDay = Math.min(...allDays)
  const maxDay = Math.max(...allDays)
  // Anchor the value axis at zero — these are supply / volume totals, so a
  // zero baseline is the honest framing for magnitude.
  const minVal = Math.min(0, ...allVals)
  const maxVal = Math.max(...allVals, 1)
  const daySpan = maxDay - minDay || 1
  const valSpan = maxVal - minVal || 1

  const x = (t: number) => pad + ((toDay(t) - minDay) / daySpan) * (width - 2 * pad)
  const y = (v: number) => height - pad - ((v - minVal) / valSpan) * (height - 2 * pad)

  return (
    <>
      <svg
        className="price-chart"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={ariaLabel}
        data-testid="trend-chart"
      >
        {drawable.map((s) => (
          <polyline
            key={s.label}
            points={s.points.map(([t, v]) => `${x(t).toFixed(1)},${y(v).toFixed(1)}`).join(" ")}
            fill="none"
            stroke={s.color}
            strokeWidth="2"
          />
        ))}
        <text x={pad} y={height - 8} className="axis-label">
          day {minDay}
        </text>
        <text x={width - pad} y={height - 8} textAnchor="end" className="axis-label">
          day {maxDay}
        </text>
        <text x={pad} y={16} className="axis-label">
          {money(maxVal)}
        </text>
      </svg>
      <ul className="chart-legend" data-testid="trend-legend">
        {drawable.map((s) => (
          <li key={s.label}>
            <span className="legend-swatch" style={{ background: s.color }} aria-hidden="true" />
            <span aria-hidden="true">{s.glyph}</span> {s.label}
            <span className="legend-count"> {money(s.points[s.points.length - 1][1])}</span>
          </li>
        ))}
      </ul>
    </>
  )
}

// The active-currency roster: ranked by trade volume, each row a bar. Minted
// vs personal is tagged in words (not colour alone), and the founder / issuance
// ride in the detail line.
function CurrencyRoster({ currencies }: { currencies: CurrencyView[] }) {
  const max = Math.max(...currencies.map((c) => c.tradeVolume), 1)
  return (
    <ul className="rank-rows" data-testid="currency-roster">
      {currencies.map((c) => (
        <li key={c.name}>
          <div className="rank-row" data-testid="currency-row">
            <span className="rank-name">
              {c.name}
              <span className="section-sub">
                {" "}
                · {c.type === "minted" ? "minted / backed" : "personal / credit"}
                {c.createdBy ? ` · by ${c.createdBy}` : ""}
              </span>
            </span>
            <span className="rank-count">
              {money(c.tradeVolume)} vol · {formatCount(c.tradeCount)} trades
              {c.isMinted ? ` · ${money(c.mintedAmount)} minted` : ""}
            </span>
            <span className="rank-bar" style={{ width: `${(c.tradeVolume / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  )
}

// Wealth distribution for one currency — top holders as balance bars, plus a
// concentration read (what share the top holder controls of the counted pool).
function WealthDistribution({ name, holders }: { name: string; holders: MoneyHolders }) {
  const rows = holders.list
  const max = Math.max(...rows.map((h) => h.balance), 1)
  const topShare =
    holders.totalHoldings > 0 && rows.length > 0 ? rows[0].balance / holders.totalHoldings : 0
  return (
    <section data-testid="wealth-distribution">
      <h2 className="section-title">
        Wealth in {name}{" "}
        <span className="section-sub">
          ({formatCount(holders.accountsCounted)} account
          {holders.accountsCounted === 1 ? "" : "s"} · {money(holders.totalHoldings)} held)
        </span>
      </h2>
      {topShare > 0 && (
        <p className="hero-pill" data-testid="wealth-concentration">
          <span className="pulse-dot" aria-hidden="true" />
          Top holder controls {pct(topShare)} of counted {name}.
        </p>
      )}
      <ul className="rank-rows" data-testid="holder-list">
        {rows.map((h) => (
          <li key={h.account}>
            <div className="rank-row" data-testid="holder-row">
              <span className="rank-name">
                {h.holder ?? h.account}
                {h.holder && h.holder !== h.account && (
                  <span className="section-sub"> · {h.account}</span>
                )}
              </span>
              <span className="rank-count">{money(h.balance)}</span>
              <span className="rank-bar" style={{ width: `${(h.balance / max) * 100}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default function Economy() {
  const [snapshot, setSnapshot] = useState<EconomySnapshot | null>(null)
  const [supply, setSupply] = useState<MoneySnapshot | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const s = controller.signal
    // Two independent planes: the KPI economy card and the richer money-supply
    // snapshot. Either can 404 without taking the page down — the money plane
    // resolves to null and its sections degrade in place.
    fetchEconomy(s)
      .then(setSnapshot)
      .catch((err) => {
        if (!s.aborted) setError(err instanceof Error ? err.message : String(err))
      })
    fetchMoney(s).then(setSupply, () => setSupply(null))
    return () => controller.abort()
  }, [])

  const k = snapshot?.kpis
  const m = supply?.money

  // The dominant currency with live holdings drives the wealth panel — the
  // roster is already ranked by trade volume, so the first reachable one is the
  // most economically active currency people actually hold.
  const wealthCurrency = useMemo(
    () => supply?.currencies.find((c) => c.holders.reachable && c.holders.list.length > 0) ?? null,
    [supply],
  )

  const supplyStats: Stat[] = m
    ? [
        { label: "Money supply", value: money(m.totalSupply), detail: "personal + government" },
        { label: "Personal wealth", value: money(m.personalWealth) },
        { label: "Government holdings", value: money(m.governmentHoldings) },
        {
          label: "Active currencies",
          value: formatCount(m.activeCurrencies),
          detail: supply
            ? `${formatCount(supply.counts.minted)} minted · ${formatCount(supply.counts.personal)} personal`
            : undefined,
        },
      ]
    : []

  const trade: Stat[] = k
    ? [
        { label: "Trades / day", value: formatCount(k.trades_per_day) },
        {
          label: "Trades all cycle",
          value: formatCount(k.trades_total),
          detail: k.trades_wow_pct ? `${pct(k.trades_wow_pct / 100)} week over week` : undefined,
        },
        {
          label: "7-day trade value",
          value: m ? money(m.tradeValue7d) : "—",
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
        { label: "Wages paid", value: money(k.wages_total) },
        { label: "Taxes paid", value: money(k.taxes_paid) },
        { label: "Government funds", value: money(k.govt_funds) },
        { label: "Total culture", value: formatCount(k.total_culture) },
      ]
    : []

  const supplySeries: TrendSeries[] = supply
    ? [
        {
          points: supply.series.personalWealth,
          color: "var(--leaf)",
          label: "Personal wealth",
          glyph: "●",
        },
        {
          points: supply.series.governmentHoldings,
          color: "var(--meteor)",
          label: "Government holdings",
          glyph: "◆",
        },
      ]
    : []

  const volumeSeries: TrendSeries[] = supply
    ? [
        {
          points: supply.series.trades7d,
          color: "var(--leaf)",
          label: "Trade value (7-day rolling)",
          glyph: "●",
        },
      ]
    : []

  const hasSupplySeries = supplySeries.some((s) => s.points.length >= 2)
  const hasVolumeSeries = volumeSeries.some((s) => s.points.length >= 2)

  return (
    <Layout fetchedAtISO={supply?.fetched_at_iso}>
      <section className="hero hero-compact">
        <p className="hero-kicker">Economy</p>
        <h1 className="hero-title">
          The <span className="accent">market pulse</span> of the world
        </h1>
        <p className="hero-tagline">
          Money supply, who holds it, the currencies in circulation, and how trade flows over the
          cycle — the whole economy on one always-on page.
        </p>
        {snapshot && (
          <p
            className={`hero-pill${snapshot.health === "healthy" ? "" : " hero-pill-warn"}`}
            data-testid="health-pill"
          >
            <span className="pulse-dot" aria-hidden="true" />
            {snapshot.narrative}
          </p>
        )}
        {supply && (
          <p className="hero-pill" data-testid="money-pill">
            <span className="pulse-dot" aria-hidden="true" />
            {supply.narrative}
          </p>
        )}
        {!snapshot && error && (
          <p className="hero-pill hero-pill-muted" data-testid="econ-error">
            economy snapshot unavailable right now
          </p>
        )}
      </section>

      {m && (
        <section data-testid="money-supply">
          <h2 className="section-title">Money supply</h2>
          <div className="stats">
            {supplyStats.map((s) => (
              <div className="stat" key={s.label}>
                <p className="stat-value">{s.value}</p>
                <p className="stat-label">{s.label}</p>
                {s.detail && <p className="stat-detail">{s.detail}</p>}
              </div>
            ))}
          </div>
          {hasSupplySeries && (
            <TrendChart series={supplySeries} ariaLabel="Money supply over in-game days" />
          )}
        </section>
      )}

      {snapshot && (
        <section data-testid="trade-flows">
          <h2 className="section-title">Trade flows</h2>
          <div className="stats">
            {trade.map((s) => (
              <div className="stat" key={s.label}>
                <p className="stat-value">{s.value}</p>
                <p className="stat-label">{s.label}</p>
                {s.detail && <p className="stat-detail">{s.detail}</p>}
              </div>
            ))}
          </div>
          {hasVolumeSeries && (
            <TrendChart series={volumeSeries} ariaLabel="Trade value over in-game days" />
          )}
        </section>
      )}

      {supply && supply.currencies.length > 0 && (
        <section data-testid="currencies">
          <h2 className="section-title">
            Active currencies{" "}
            <span className="section-sub">
              ({formatCount(supply.counts.total)} in circulation — ranked by trade volume)
            </span>
          </h2>
          <CurrencyRoster currencies={supply.currencies} />
        </section>
      )}

      {wealthCurrency && (
        <WealthDistribution name={wealthCurrency.name} holders={wealthCurrency.holders} />
      )}

      {supply && !wealthCurrency && supply.currencies.length > 0 && (
        <section>
          <p className="empty-note" data-testid="wealth-unavailable">
            {supply.holders_reachable
              ? "No accounts hold a balance yet — wealth distribution fills in as currency changes hands."
              : supply.holders_unavailable_note}
          </p>
        </section>
      )}

      {k && (
        <section data-testid="treasury">
          <h2 className="section-title">Treasury &amp; culture</h2>
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
      )}

      {snapshot && (
        <section className="dir-cards">
          <Link className="dir-card" to="/trade" data-testid="link-trade">
            <h3>Trade &amp; logistics →</h3>
            <p>Price movers, per-item history, every store, and what to buy, sell, and ship next.</p>
          </Link>
          <Link className="dir-card" to="/trades" data-testid="link-trades">
            <h3>Trades ledger →</h3>
            <p>
              The row-level view behind those {formatCount(snapshot.kpis.trades_total)} trades — who
              sold what to whom, and price over time.
            </p>
          </Link>
          <Link className="dir-card" to="/crafting" data-testid="link-crafting">
            <h3>Crafting atlas →</h3>
            <p>
              The production side of those {formatCount(snapshot.kpis.trades_total)} trades — what's
              being made, where, and from what.
            </p>
          </Link>
        </section>
      )}
    </Layout>
  )
}
