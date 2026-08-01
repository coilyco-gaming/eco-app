import { useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"
import ItemLink from "../components/ItemLink"
import Layout from "../components/Layout"
import {
  fetchFoodReport,
  type FoodReport,
  type FoodSignal,
  type FoodSignalKind,
} from "../lib/foodApi"
import { formatCount } from "../lib/format"

const SIGNALS: Record<FoodSignalKind, { label: string; tone: string }> = {
  restock: { label: "restock", tone: "var(--meteor)" },
  balanced: { label: "balanced", tone: "var(--moss)" },
  potential_overstock: { label: "potential overstock", tone: "var(--meteor-deep)" },
  insufficient: { label: "insufficient data", tone: "var(--ink-faint)" },
}

function FoodRow({ row }: { row: FoodSignal }) {
  const signal = SIGNALS[row.signal]
  const query = encodeURIComponent(row.item)
  return (
    <li className="gap-row" data-testid="food-row">
      <div className="gap-head">
        <ItemLink className="linklike gap-name" item={row.item}>
          {row.itemPretty}
        </ItemLink>
        <span className="gap-tag" style={{ color: signal.tone }} data-testid="food-signal">
          {signal.label}
        </span>
      </div>
      <p className="gap-summary">{row.reason}</p>
      <p className="gap-who">
        shelf supply {formatCount(row.supplyQty)} · demand {formatCount(row.demandQty)} · {formatCount(row.tradeCount)} trades · {formatCount(row.craftCount)} crafted
      </p>
      <p className="gap-who">
        <Link className="linklike" to={`/trade?q=${query}`}>trade</Link>{" · "}
        <Link className="linklike" to={`/recipes?q=${query}`}>recipe</Link>{" · "}
        <Link className="linklike" to={`/uses/price?item=${query}`}>pricing</Link>
      </p>
    </li>
  )
}

export default function UsesFood() {
  const [report, setReport] = useState<FoodReport | null>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    fetchFoodReport(controller.signal)
      .then(setReport)
      .finally(() => {
        if (!controller.signal.aborted) setLoaded(true)
      })
    return () => controller.abort()
  }, [])

  const rows = useMemo(() => report?.signals ?? [], [report])
  return (
    <Layout fetchedAtISO={report?.fetchedAtISO}>
      <section className="hero hero-compact">
        <p className="hero-kicker"><Link to="/uses" className="linklike">← Use cases</Link></p>
        <h1 className="hero-title">Food <span className="accent">restock signals</span></h1>
        <p className="hero-tagline">
          Confirmed cooking, baking, and chef recipe products only. Unknown item classes are excluded.
        </p>
      </section>
      {!loaded && <p className="empty-note">Reading food shelves and production…</p>}
      {loaded && !report && <p className="empty-note" data-testid="food-unavailable">Food data is unavailable right now.</p>}
      {report && rows.length === 0 && <p className="empty-note" data-testid="food-empty">No confirmed food products have matching market evidence yet.</p>}
      {rows.length > 0 && (
        <section data-testid="food-list">
          <h2 className="section-title">Food decisions <span className="section-sub">({formatCount(rows.length)} confirmed products)</span></h2>
          <ul className="gap-list">{rows.map((row) => <FoodRow key={row.item} row={row} />)}</ul>
        </section>
      )}
      {report?.warnings.length ? <ul className="warn-list">{report.warnings.map((warning) => <li key={warning}>⚠ {warning}</li>)}</ul> : null}
    </Layout>
  )
}
