import { useEffect, useMemo, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import Layout from "../components/Layout"
import { fetchTradesLedger, type Trade, type TradesLedger } from "../lib/tradesApi"
import { fetchWatchers, type WatcherHit } from "../lib/watchersApi"
import { formatCount, prettifyEcoName } from "../lib/format"

const TOP_N = 15
const LEDGER_ROWS = 60

// Compact inline SVG line of mean unit price per in-game day. No chart lib —
// the SPA has no shared chart component and this is a single sparkline, so a
// hand-rolled polyline keeps the bundle lean and CSP trivial.
function PriceChart({ points }: { points: Array<[number, number]> }) {
  const width = 620
  const height = 160
  const pad = 28
  if (points.length < 2) {
    return <p className="empty-note">Not enough price history to chart yet.</p>
  }
  const days = points.map(([d]) => d)
  const prices = points.map(([, p]) => p)
  const minDay = Math.min(...days)
  const maxDay = Math.max(...days)
  const minPrice = Math.min(...prices)
  const maxPrice = Math.max(...prices)
  const daySpan = maxDay - minDay || 1
  const priceSpan = maxPrice - minPrice || 1

  const x = (d: number) => pad + ((d - minDay) / daySpan) * (width - 2 * pad)
  const y = (p: number) => height - pad - ((p - minPrice) / priceSpan) * (height - 2 * pad)
  const line = points.map(([d, p]) => `${x(d).toFixed(1)},${y(p).toFixed(1)}`).join(" ")

  return (
    <svg
      className="price-chart"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Mean unit price by in-game day"
      data-testid="price-chart"
    >
      <polyline points={line} fill="none" stroke="var(--leaf)" strokeWidth="2" />
      {points.map(([d, p]) => (
        <circle key={d} cx={x(d)} cy={y(p)} r="3" fill="var(--meteor)">
          <title>
            Day {d}: {p.toFixed(2)}
          </title>
        </circle>
      ))}
      <text x={pad} y={height - 6} className="axis-label">
        day {minDay}
      </text>
      <text x={width - pad} y={height - 6} textAnchor="end" className="axis-label">
        day {maxDay}
      </text>
      <text x={pad} y={16} className="axis-label">
        {maxPrice.toFixed(1)}
      </text>
      <text x={pad} y={height - pad + 12} className="axis-label">
        {minPrice.toFixed(1)}
      </text>
    </svg>
  )
}

interface TraderListProps {
  rows: Array<[string, number]>
}

// Ranked bar list of parties by currency. Names arrive already resolved from
// the server's id→name join, so they show verbatim (no Eco-id prettifying).
function TraderList({ rows }: TraderListProps) {
  const top = rows.slice(0, TOP_N)
  const max = Math.max(...top.map(([, amt]) => amt), 1)
  if (top.length === 0) {
    return <p className="empty-note">No currency movement recorded.</p>
  }
  return (
    <ul className="rank-rows">
      {top.map(([name, amt]) => (
        <li key={name}>
          <div className="rank-row" data-testid="trader-row">
            <span className="rank-name">{name}</span>
            <span className="rank-count">{formatCount(amt)}</span>
            <span className="rank-bar" style={{ width: `${(amt / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  )
}

// Read-only sidebar of the stored trade watchers and what they currently catch.
// Watchers are created / removed over MCP (`eco_trade_watchers`); this surface
// just shows the list and each watcher's live matching state (the display
// semantic), plus a "new since last check" badge (the feed count). Rendered only
// when at least one watcher exists — an empty store shows nothing here.
function WatcherList({ hits }: { hits: WatcherHit[] }) {
  return (
    <ul className="rank-rows" data-testid="watcher-list">
      {hits.map((h) => (
        <li key={h.id}>
          <div className="rank-row" data-testid="watcher-row">
            <span className="rank-name">
              {h.label}
              {h.feedCount > 0 && (
                <span className="watcher-badge" data-testid="watcher-badge">
                  {" "}
                  +{formatCount(h.feedCount)} new
                </span>
              )}
            </span>
            <span className="rank-count">
              {formatCount(h.display.matchCount)} match
              {h.display.bestUnitPrice !== null
                ? ` · cheapest ${formatCount(h.display.bestUnitPrice)}`
                : ""}
            </span>
          </div>
        </li>
      ))}
    </ul>
  )
}

function matchesTrade(t: Trade, needle: string): boolean {
  if (!needle) return true
  const hay = [t.seller, t.buyer, prettifyEcoName(t.item), t.currency]
    .join(" ")
    .toLowerCase()
  return hay.includes(needle)
}

export default function Trades() {
  const [ledger, setLedger] = useState<TradesLedger | null>(null)
  const [watchers, setWatchers] = useState<WatcherHit[]>([])
  const [error, setError] = useState<string | null>(null)
  const [params, setParams] = useSearchParams()
  const q = params.get("q") ?? ""
  const [selectedItem, setSelectedItem] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchTradesLedger(controller.signal)
      .then(setLedger)
      .catch((err) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err))
      })
    // Watchers are a best-effort sidebar — fetchWatchers already swallows a
    // failing / empty store into [], so this never surfaces an error state.
    fetchWatchers(controller.signal)
      .then(setWatchers)
      .catch(() => {
        /* non-fatal: leave the watcher sidebar empty */
      })
    return () => controller.abort()
  }, [])

  const setQuery = (value: string) => {
    setParams(value ? { q: value } : {}, { replace: false })
  }

  // Default the price chart to the highest-volume item that has a series.
  const pricedItems = useMemo(
    () => (ledger ? Object.keys(ledger.priceSeries) : []),
    [ledger],
  )
  const chartItem = useMemo(() => {
    if (!ledger) return null
    if (selectedItem && ledger.priceSeries[selectedItem]) return selectedItem
    for (const [item] of ledger.byItem) {
      if (ledger.priceSeries[item]) return item
    }
    return pricedItems[0] ?? null
  }, [ledger, selectedItem, pricedItems])

  const needle = q.trim().toLowerCase()
  const visibleTrades = useMemo(
    () => (ledger ? ledger.trades.filter((t) => matchesTrade(t, needle)).slice(0, LEDGER_ROWS) : []),
    [ledger, needle],
  )

  return (
    <Layout>
      <section className="hero hero-compact">
        <p className="hero-kicker">Trades ledger</p>
        <h1 className="hero-title">
          Every <span className="accent">trade</span>, row by row
        </h1>
        {ledger && (
          <p className="hero-pill" data-testid="trades-pill">
            <span className="pulse-dot" aria-hidden="true" />
            {formatCount(ledger.totalTrades)} trades · {formatCount(ledger.totalCurrencyVolume)}{" "}
            currency moved
          </p>
        )}
        {!ledger && error && (
          <p className="hero-pill hero-pill-muted" data-testid="trades-error">
            trades ledger unavailable right now
          </p>
        )}
      </section>

      {ledger && ledger.totalTrades === 0 && (
        <section>
          <p className="empty-note" data-testid="trades-empty">
            No trades recorded on this server yet. Early in a cycle this is normal — check back
            after a few days of play.
          </p>
        </section>
      )}

      {ledger && ledger.totalTrades > 0 && (
        <>
          {chartItem && ledger.priceSeries[chartItem] && (
            <section>
              <h2 className="section-title">
                Price over time — {prettifyEcoName(chartItem)}
              </h2>
              {pricedItems.length > 1 && (
                <div className="filter-row">
                  <select
                    className="filter-input"
                    value={chartItem}
                    onChange={(e) => setSelectedItem(e.target.value)}
                    data-testid="price-item-select"
                  >
                    {ledger.byItem
                      .filter(([item]) => ledger.priceSeries[item])
                      .map(([item]) => (
                        <option key={item} value={item}>
                          {prettifyEcoName(item)}
                        </option>
                      ))}
                  </select>
                </div>
              )}
              <PriceChart points={ledger.priceSeries[chartItem]} />
            </section>
          )}

          <section className="filter-row">
            <input
              className="filter-input"
              type="search"
              placeholder="Filter by buyer, seller, item, or currency… (deep-linkable as ?q=)"
              value={q}
              onChange={(e) => setQuery(e.target.value)}
              data-testid="trades-filter"
            />
            {q && (
              <button className="button" onClick={() => setQuery("")}>
                Clear
              </button>
            )}
          </section>

          <section>
            <h2 className="section-title">
              Ledger {q ? `matching "${q}"` : ""}{" "}
              <span className="section-sub">
                (newest {visibleTrades.length}
                {ledger.trades.length > visibleTrades.length
                  ? ` of ${formatCount(ledger.trades.length)}`
                  : ""}
                )
              </span>
            </h2>
            {visibleTrades.length === 0 ? (
              <p className="empty-note">No trades match.</p>
            ) : (
              <table className="ledger-table" data-testid="trades-table">
                <thead>
                  <tr>
                    <th>Day</th>
                    <th>Seller</th>
                    <th>Buyer</th>
                    <th>Item</th>
                    <th className="num">Qty</th>
                    <th className="num">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleTrades.map((t, i) => (
                    <tr key={`${t.time}-${i}`} data-testid="trade-row">
                      <td>{Math.floor(t.day)}</td>
                      <td>{t.seller || "—"}</td>
                      <td>{t.buyer || "—"}</td>
                      <td>
                        {t.item ? (
                          <button className="linklike" onClick={() => setQuery(prettifyEcoName(t.item))}>
                            {prettifyEcoName(t.item)}
                          </button>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="num">{formatCount(t.quantity)}</td>
                      <td className="num">
                        {t.currencyAmount
                          ? `${formatCount(t.currencyAmount)} ${t.currency}`.trim()
                          : t.tradeType === "BarterTrade"
                            ? "barter"
                            : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          {watchers.length > 0 && (
            <section data-testid="watchers-section">
              <h2 className="section-title">
                Trade watchers{" "}
                <span className="section-sub">
                  ({watchers.length} watching — manage over MCP)
                </span>
              </h2>
              <WatcherList hits={watchers} />
            </section>
          )}

          <div className="atlas-columns">
            <section>
              <h2 className="section-title">Top sellers</h2>
              <TraderList rows={ledger.topSellers} />
            </section>
            <section>
              <h2 className="section-title">Top buyers</h2>
              <TraderList rows={ledger.topBuyers} />
            </section>
          </div>

          {ledger.warnings.length > 0 && (
            <section>
              <ul className="warn-list" data-testid="trades-warnings">
                {ledger.warnings.map((w) => (
                  <li key={w}>⚠ {w}</li>
                ))}
              </ul>
            </section>
          )}

          <section className="dir-cards">
            <Link className="dir-card" to="/trade" data-testid="link-trade">
              <h3>Trade &amp; logistics →</h3>
              <p>The aggregate view — movers, price history, stores, and what to trade next.</p>
            </Link>
            <Link className="dir-card" to="/crafting" data-testid="link-crafting">
              <h3>Crafting atlas →</h3>
              <p>Where the traded goods come from — what's being made, where, and from what.</p>
            </Link>
          </section>
        </>
      )}
    </Layout>
  )
}
