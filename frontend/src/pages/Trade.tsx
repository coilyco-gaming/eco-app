import { useEffect, useMemo, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import Layout from "../components/Layout"
import { fetchMarket, type ItemMarket, type MarketIntelligence, type MarketTrend } from "../lib/marketApi"
import { fetchStores, type StoreDirectory } from "../lib/storesApi"
import { fetchCurrency, type CurrencySnapshot } from "../lib/currencyApi"
import { fetchLogistics, type GapReason, type LogisticsBoard, type SupplyGap } from "../lib/logisticsApi"
import { fetchWatchers, type WatcherHit } from "../lib/watchersApi"
import { formatCount } from "../lib/format"

const TOP_MOVERS = 6
const TOP_TRADED = 12
const DIR_ROWS = 10
const LOGI_ROWS = 8

// Prices carry fractional cents; formatCount rounds to whole units, so trade
// surfaces get their own 2-dp formatter.
function fmtPrice(n: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(n)
}

// Trend is encoded glyph + label + colour (never colour alone, per the dataviz
// non-negotiables): rising leans on the leaf green, falling on meteor amber,
// flat/insufficient stay muted ink.
const TREND: Record<MarketTrend, { glyph: string; label: string; color: string }> = {
  rising: { glyph: "▲", label: "rising", color: "var(--leaf)" },
  falling: { glyph: "▼", label: "falling", color: "var(--meteor)" },
  flat: { glyph: "▬", label: "flat", color: "var(--ink-faint)" },
  insufficient: { glyph: "·", label: "thin", color: "var(--ink-faint)" },
}

function TrendTag({ trend, delta }: { trend: MarketTrend; delta: number | null }) {
  const t = TREND[trend]
  const pct = delta !== null && trend !== "flat" && trend !== "insufficient"
    ? ` ${delta > 0 ? "+" : ""}${Math.round(delta)}%`
    : ""
  return (
    <span className="trend-tag" style={{ color: t.color }} data-testid="trend-tag">
      <span aria-hidden="true">{t.glyph}</span> {t.label}
      {pct}
    </span>
  )
}

// Supply-gap severity, encoded glyph + label + colour (never colour alone, per
// the dataviz non-negotiables): an unmet buy order is the loudest (meteor
// amber), a lone monopolist is thin supply (bark), a merely over-priced shelf
// stays muted ink.
const GAP: Record<GapReason, { glyph: string; label: string; color: string }> = {
  no_supply: { glyph: "✖", label: "no supply", color: "var(--meteor)" },
  thin_supply: { glyph: "◐", label: "thin supply", color: "var(--meteor-deep)" },
  overpriced: { glyph: "▲", label: "over-priced", color: "var(--ink-faint)" },
}

// One supply gap: the item, a reason tag, and — the point of eco-app#77 — WHO
// needs it. A gap is only actionable if you know who is asking, so the buy-side
// citizens and how much each still wants get their own line rather than being
// crushed into the narrow count column.
function SupplyGapRow({ gap, onPick }: { gap: SupplyGap; onPick: (item: string) => void }) {
  const g = GAP[gap.reason]
  const summary =
    gap.reason === "overpriced"
      ? `cheapest ${fmtPrice(gap.cheapestSell ?? 0)} vs median ${fmtPrice(gap.median ?? 0)}` +
        (gap.overMedianPct !== null ? ` (+${Math.round(gap.overMedianPct)}%)` : "")
      : `${formatCount(gap.demandQty)} wanted · ${formatCount(gap.buyerCount)} buyer${
          gap.buyerCount === 1 ? "" : "s"
        } · ${formatCount(gap.sellerCount)} seller${gap.sellerCount === 1 ? "" : "s"}`
  return (
    <li className="gap-row" data-testid="gap-row">
      <div className="gap-head">
        <button className="linklike gap-name" onClick={() => onPick(gap.itemPretty)}>
          {gap.itemPretty}
        </button>
        <span className="gap-tag" style={{ color: g.color }} data-testid="gap-tag">
          <span aria-hidden="true">{g.glyph}</span> {g.label}
        </span>
      </div>
      <p className="gap-summary">{summary}</p>
      {gap.buyers.length > 0 && (
        <p className="gap-who" data-testid="gap-who">
          <span className="gap-who-label">Who needs it:</span>{" "}
          {gap.buyers.map((b, i) => (
            <span key={`${b.owner}-${b.store}-${i}`} className="gap-buyer">
              {b.owner || b.store} <span className="gap-buyer-qty">{formatCount(b.quantity)}</span>
              {i < gap.buyers.length - 1 ? ", " : ""}
            </span>
          ))}
        </p>
      )}
    </li>
  )
}

// Compact inline SVG line of an item's median unit price per in-game day. No
// chart lib — a single sparkline keeps the bundle lean and CSP trivial, matching
// the sibling /trades chart.
function PriceChart({ points }: { points: Array<[number, number]> }) {
  const width = 620
  const height = 160
  const pad = 28
  if (points.length < 2) {
    return <p className="empty-note">Not enough price history to chart this item yet.</p>
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
      aria-label="Median unit price by in-game day"
      data-testid="price-chart"
    >
      <polyline points={line} fill="none" stroke="var(--leaf)" strokeWidth="2" />
      {points.map(([d, p]) => (
        <circle key={d} cx={x(d)} cy={y(p)} r="3" fill="var(--meteor)">
          <title>
            Day {d}: {fmtPrice(p)}
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
        {fmtPrice(maxPrice)}
      </text>
      <text x={pad} y={height - pad + 12} className="axis-label">
        {fmtPrice(minPrice)}
      </text>
    </svg>
  )
}

// A ranked, clickable list of markets — used for movers and most-traded. A
// click deep-links the drill-down via ?q=, the same interaction the /trades and
// /crafting pages use.
function MarketList({
  rows,
  onPick,
  testid,
}: {
  rows: ItemMarket[]
  onPick: (item: string) => void
  testid: string
}) {
  if (rows.length === 0) {
    return <p className="empty-note">Nothing here yet.</p>
  }
  const max = Math.max(...rows.map((m) => m.totalVolume), 1)
  return (
    <ul className="rank-rows" data-testid={testid}>
      {rows.map((m) => (
        <li key={`${m.item}-${m.currency}`}>
          <button className="rank-row" onClick={() => onPick(m.itemPretty)} data-testid="market-row">
            <span className="rank-name">{m.itemPretty}</span>
            <span className="rank-count">
              {fmtPrice(m.latestPrice)} {m.currency} · <TrendTag trend={m.trend} delta={m.trendDeltaPct} />
            </span>
            <span className="rank-bar" style={{ width: `${(m.totalVolume / max) * 100}%` }} />
          </button>
        </li>
      ))}
    </ul>
  )
}

// Read-only sidebar of the stored trade watchers and their current hits —
// mirrors the /trades panel. Watchers are managed over MCP; this is display
// only.
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
              {h.display.bestUnitPrice !== null ? ` · cheapest ${fmtPrice(h.display.bestUnitPrice)}` : ""}
            </span>
          </div>
        </li>
      ))}
    </ul>
  )
}

export default function Trade() {
  const [market, setMarket] = useState<MarketIntelligence | null>(null)
  const [stores, setStores] = useState<StoreDirectory | null>(null)
  const [currency, setCurrency] = useState<CurrencySnapshot | null>(null)
  const [logistics, setLogistics] = useState<LogisticsBoard | null>(null)
  const [watchers, setWatchers] = useState<WatcherHit[]>([])
  const [loaded, setLoaded] = useState(false)
  const [params, setParams] = useSearchParams()
  const q = params.get("q") ?? ""

  useEffect(() => {
    const controller = new AbortController()
    const s = controller.signal
    // Every plane is best-effort and independent: siblings land on their own
    // schedule, so one 404 must never take the page down. Each resolves to null
    // (or [] for watchers) and its panel degrades in place.
    Promise.all([
      fetchMarket(s).then(setMarket, () => setMarket(null)),
      fetchStores(s).then(setStores, () => setStores(null)),
      fetchCurrency(s).then(setCurrency, () => setCurrency(null)),
      fetchLogistics(s).then(setLogistics, () => setLogistics(null)),
      fetchWatchers(s).then(setWatchers, () => setWatchers([])),
    ]).finally(() => {
      if (!s.aborted) setLoaded(true)
    })
    return () => controller.abort()
  }, [])

  const setQuery = (value: string) => {
    setParams(value ? { q: value } : {}, { replace: false })
  }

  const markets = useMemo(() => market?.markets ?? [], [market])
  const needle = q.trim().toLowerCase()

  const risers = useMemo(
    () =>
      markets
        .filter((m) => m.trend === "rising")
        .sort((a, b) => (b.trendDeltaPct ?? 0) - (a.trendDeltaPct ?? 0))
        .slice(0, TOP_MOVERS),
    [markets],
  )
  const fallers = useMemo(
    () =>
      markets
        .filter((m) => m.trend === "falling")
        .sort((a, b) => (a.trendDeltaPct ?? 0) - (b.trendDeltaPct ?? 0))
        .slice(0, TOP_MOVERS),
    [markets],
  )
  const mostTraded = useMemo(() => markets.slice(0, TOP_TRADED), [markets])
  const totalVolume = useMemo(() => markets.reduce((sum, m) => sum + m.totalVolume, 0), [markets])

  // The drilled item: the ?q= match if there is one, else the busiest market.
  const drill = useMemo(() => {
    if (markets.length === 0) return null
    if (needle) {
      const hit = markets.find(
        (m) => m.itemPretty.toLowerCase().includes(needle) || m.item.toLowerCase().includes(needle),
      )
      if (hit) return hit
    }
    return markets[0]
  }, [markets, needle])

  const drillPoints = useMemo<Array<[number, number]>>(
    () => (drill ? drill.buckets.map((b) => [b.day, b.median]) : []),
    [drill],
  )
  const drillSource = useMemo(() => {
    if (!drill || !logistics) return null
    const row = logistics.cheapest.find(
      (c) => c.item === drill.item || c.itemPretty.toLowerCase() === drill.itemPretty.toLowerCase(),
    )
    const best = row?.offers[0]
    if (!row || !best) return null
    return { unitPrice: best.price, currency: row.currency, store: best.store, owner: best.owner }
  }, [drill, logistics])

  const topStores = useMemo(
    () => (stores ? [...stores.stores].sort((a, b) => b.totalVolume - a.totalVolume).slice(0, DIR_ROWS) : []),
    [stores],
  )
  const topTraders = useMemo(
    () => (stores ? [...stores.traders].sort((a, b) => b.totalVolume - a.totalVolume).slice(0, DIR_ROWS) : []),
    [stores],
  )

  const nothing =
    loaded && !market && !stores && !currency && !logistics && watchers.length === 0

  return (
    <Layout fetchedAtISO={market?.fetchedAtISO ?? stores?.fetchedAtISO}>
      <section className="hero hero-compact">
        <p className="hero-kicker">Trade &amp; store logistics</p>
        <h1 className="hero-title">
          What to <span className="accent">buy, sell, and ship</span>
        </h1>
        <p className="hero-tagline">
          The whole market on one always-on page — movers, price history, every store, and the
          logistics of what to do next. The website answer to Discord's ephemeral DM embeds.
        </p>
        {market && (
          <p className="hero-pill" data-testid="trade-pill">
            <span className="pulse-dot" aria-hidden="true" />
            {formatCount(markets.length)} markets · {formatCount(totalVolume)} volume ·{" "}
            {formatCount(market.totalTrades)} trades
          </p>
        )}
        {nothing && (
          <p className="hero-pill hero-pill-muted" data-testid="trade-error">
            trade data unavailable right now — check back once the game server has traded
          </p>
        )}
      </section>

      {!loaded && (
        <p className="empty-note" data-testid="trade-loading">
          Loading the market…
        </p>
      )}

      {/* Currency strip — money-supply summary. */}
      {currency && (
        <section data-testid="currency-strip">
          <h2 className="section-title">
            Money supply{" "}
            <span className="section-sub">
              ({formatCount(currency.currencies.length)} currenc
              {currency.currencies.length === 1 ? "y" : "ies"} in circulation)
            </span>
          </h2>
          <div className="stats">
            <div className="stat">
              <p className="stat-value">{formatCount(currency.currencies.length)}</p>
              <p className="stat-label">Currencies</p>
            </div>
            <div className="stat">
              <p className="stat-value">
                {formatCount(currency.currencies.reduce((s, c) => s + c.mintedAmount, 0))}
              </p>
              <p className="stat-label">Total minted</p>
            </div>
            <div className="stat">
              <p className="stat-value">
                {formatCount(currency.currencies.reduce((s, c) => s + c.tradeVolume, 0))}
              </p>
              <p className="stat-label">Traded volume</p>
            </div>
            <div className="stat">
              <p className="stat-value">{formatCount(currency.daysElapsed)}</p>
              <p className="stat-label">Days elapsed</p>
            </div>
          </div>
        </section>
      )}

      {/* Market overview — movers + most-traded. */}
      {market && markets.length > 0 && (
        <>
          <section className="atlas-columns" data-testid="movers">
            <div>
              <h2 className="section-title">Rising</h2>
              <MarketList rows={risers} onPick={setQuery} testid="risers" />
            </div>
            <div>
              <h2 className="section-title">Falling</h2>
              <MarketList rows={fallers} onPick={setQuery} testid="fallers" />
            </div>
          </section>

          <section>
            <h2 className="section-title">
              Most traded <span className="section-sub">(by volume — click to drill in)</span>
            </h2>
            <MarketList rows={mostTraded} onPick={setQuery} testid="most-traded" />
          </section>
        </>
      )}

      {market && markets.length === 0 && (
        <section>
          <p className="empty-note" data-testid="market-empty">
            No priced markets yet. Early in a cycle this is normal — check back after a few days of
            trading.
          </p>
        </section>
      )}

      {/* Item drill-down. */}
      {drill && (
        <section data-testid="drill">
          <h2 className="section-title">
            {drill.itemPretty}{" "}
            <span className="section-sub">
              ({drill.currency} · <TrendTag trend={drill.trend} delta={drill.trendDeltaPct} />)
            </span>
          </h2>
          <div className="filter-row">
            <input
              className="filter-input"
              type="search"
              placeholder="Drill into an item… (deep-linkable as ?q=)"
              value={q}
              onChange={(e) => setQuery(e.target.value)}
              data-testid="trade-filter"
            />
            {q && (
              <button className="button" onClick={() => setQuery("")}>
                Clear
              </button>
            )}
          </div>
          <div className="stats">
            <div className="stat">
              <p className="stat-value">{fmtPrice(drill.latestPrice)}</p>
              <p className="stat-label">Latest price</p>
              <p className="stat-detail">day {drill.latestDay}</p>
            </div>
            <div className="stat">
              <p className="stat-value">{fmtPrice(drill.medianPrice)}</p>
              <p className="stat-label">Median price</p>
            </div>
            <div className="stat">
              <p className="stat-value">{formatCount(drill.totalVolume)}</p>
              <p className="stat-label">Units traded</p>
            </div>
            <div className="stat">
              <p className="stat-value">{formatCount(drill.totalTrades)}</p>
              <p className="stat-label">Trades</p>
            </div>
          </div>
          <PriceChart points={drillPoints} />
          {drillSource && (
            <p className="hero-pill" data-testid="drill-source">
              Cheapest right now: {fmtPrice(drillSource.unitPrice)} {drillSource.currency} at{" "}
              {drillSource.store} ({drillSource.owner})
            </p>
          )}
          <p className="section-sub">
            <Link className="linklike" to={`/trades?q=${encodeURIComponent(drill.itemPretty)}`}>
              See every {drill.itemPretty} trade in the ledger →
            </Link>
          </p>
        </section>
      )}

      {/* Logistics board — the headline "what should I do" panel. */}
      {logistics &&
        (logistics.cheapest.length > 0 ||
          logistics.arbitrage.length > 0 ||
          logistics.supplyGaps.length > 0) && (
          <section data-testid="logistics">
            <h2 className="section-title">
              Logistics <span className="section-sub">(what to do next)</span>
            </h2>
            {logistics.arbitrage.length > 0 && (
              <>
                <h3 className="card-title">Arbitrage spreads</h3>
                <table className="ledger-table" data-testid="arbitrage-table">
                  <thead>
                    <tr>
                      <th>Item</th>
                      <th>Buy at</th>
                      <th>Sell at</th>
                      <th className="num">Spread</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logistics.arbitrage.slice(0, LOGI_ROWS).map((a) => (
                      <tr
                        key={`${a.item}-${a.buyFrom.storeKey}-${a.sellTo.storeKey}`}
                        data-testid="arbitrage-row"
                      >
                        <td>
                          <button className="linklike" onClick={() => setQuery(a.itemPretty)}>
                            {a.itemPretty}
                          </button>
                        </td>
                        <td>
                          {fmtPrice(a.buyFrom.price)} — {a.buyFrom.store}
                        </td>
                        <td>
                          {fmtPrice(a.sellTo.price)} — {a.sellTo.store}
                        </td>
                        <td className="num">
                          +{fmtPrice(a.spread)} {a.currency} ({Math.round(a.spreadPct)}%)
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
            {logistics.cheapest.length > 0 && (
              <>
                <h3 className="card-title">Cheapest source</h3>
                <ul className="rank-rows" data-testid="cheapest-list">
                  {logistics.cheapest.slice(0, LOGI_ROWS).map((c) => {
                    const best = c.offers[0]
                    return (
                      <li key={`${c.item}-${c.currency}`}>
                        <div className="rank-row">
                          <span className="rank-name">{c.itemPretty}</span>
                          <span className="rank-count">
                            {fmtPrice(c.cheapest ?? best?.price ?? 0)} {c.currency}
                            {best ? ` · ${best.store} (${best.owner})` : ""}
                          </span>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              </>
            )}
            {logistics.supplyGaps.length > 0 && (
              <>
                <h3 className="card-title">
                  Supply gaps <span className="section-sub">(what to stock — and who needs it)</span>
                </h3>
                <ul className="gap-list" data-testid="gaps-list">
                  {logistics.supplyGaps.slice(0, LOGI_ROWS).map((g) => (
                    <SupplyGapRow key={`${g.item}-${g.currency}`} gap={g} onPick={setQuery} />
                  ))}
                </ul>
              </>
            )}
          </section>
        )}

      {/* Store & trader directory. */}
      {stores && (stores.stores.length > 0 || stores.traders.length > 0) && (
        <section className="atlas-columns" data-testid="directory">
          <div>
            <h2 className="section-title">
              Stores <span className="section-sub">({formatCount(stores.totalStores)})</span>
            </h2>
            {topStores.length === 0 ? (
              <p className="empty-note">No stores recorded yet.</p>
            ) : (
              <ul className="rank-rows" data-testid="store-list">
                {topStores.map((st) => {
                  const max = Math.max(...topStores.map((x) => x.totalVolume), 1)
                  return (
                    <li key={st.storeKey}>
                      <div className="rank-row" data-testid="store-row">
                        <span className="rank-name">
                          {st.label}
                          <span className="section-sub"> · {st.owner}</span>
                        </span>
                        <span className="rank-count">{formatCount(st.totalVolume)}</span>
                        <span className="rank-bar" style={{ width: `${(st.totalVolume / max) * 100}%` }} />
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
          <div>
            <h2 className="section-title">
              Traders <span className="section-sub">({formatCount(stores.totalTraders)})</span>
            </h2>
            {topTraders.length === 0 ? (
              <p className="empty-note">No traders recorded yet.</p>
            ) : (
              <ul className="rank-rows" data-testid="trader-list">
                {topTraders.map((tr) => {
                  const max = Math.max(...topTraders.map((x) => x.totalVolume), 1)
                  return (
                    <li key={tr.citizenId || tr.name}>
                      <div className="rank-row" data-testid="trader-dir-row">
                        <span className="rank-name">{tr.name}</span>
                        <span className="rank-count">{formatCount(tr.totalVolume)}</span>
                        <span className="rank-bar" style={{ width: `${(tr.totalVolume / max) * 100}%` }} />
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </section>
      )}

      {/* Watchers panel. */}
      {watchers.length > 0 && (
        <section data-testid="watchers-section">
          <h2 className="section-title">
            Your trade watchers{" "}
            <span className="section-sub">({watchers.length} watching — manage over MCP)</span>
          </h2>
          <WatcherList hits={watchers} />
        </section>
      )}

      {/* Cross-links. */}
      {loaded && (
        <section className="dir-cards">
          <Link className="dir-card" to="/economy" data-testid="link-economy">
            <h3>Economy →</h3>
            <p>The aggregate view — trades per day, contracts, loans, and the treasury.</p>
          </Link>
          <Link className="dir-card" to="/trades" data-testid="link-trades">
            <h3>Trades ledger →</h3>
            <p>Every individual trade, row by row — who sold what to whom.</p>
          </Link>
          <Link className="dir-card" to="/crafting" data-testid="link-crafting">
            <h3>Crafting atlas →</h3>
            <p>Where the traded goods come from — what's made, where, and from what.</p>
          </Link>
        </section>
      )}
    </Layout>
  )
}
