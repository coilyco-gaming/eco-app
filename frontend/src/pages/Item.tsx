import { useEffect, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import Layout from "../components/Layout"
import { fetchItemPivot, type ItemPivot } from "../lib/itemsApi"
import { formatCount, prettifyEcoName } from "../lib/format"

// Maps the raw production action id to a past-tense verb for the pivot lines.
const ACTION_VERBS: Record<string, string> = {
  ItemCraftedAction: "crafted",
  HarvestOrHunt: "harvested",
  ChopTree: "felled",
  DigOrMine: "mined",
}

const EVENT_ROWS = 200

function pricePhrase(unitPrice: number | null, currency: string): string {
  if (unitPrice === null || !currency) return ""
  return ` @ ${formatCount(unitPrice)} ${currency}`.trimEnd()
}

// Per-item pivot: every trade and crafting event that pivots on one item id.
// The item id arrives via ?item=<id> (deep-linked from the /items directory).
export default function Item() {
  const [params] = useSearchParams()
  const item = params.get("item") ?? ""
  const [fetched, setFetched] = useState<ItemPivot | null>(null)
  const [erroredItem, setErroredItem] = useState<string | null>(null)

  useEffect(() => {
    if (!item) return
    const controller = new AbortController()
    fetchItemPivot(item, controller.signal)
      .then(setFetched)
      .catch(() => {
        if (!controller.signal.aborted) setErroredItem(item)
      })
    return () => controller.abort()
  }, [item])

  // Gate on the item the state belongs to, so switching items shows a clean
  // loading gap rather than the previous item's data (and avoids resetting
  // state inside the effect).
  const pivot = fetched && fetched.item === item ? fetched : null
  const error = erroredItem === item
  const pretty = item ? prettifyEcoName(item) : ""

  return (
    <Layout fetchedAtISO={pivot?.fetchedAtISO}>
      <section className="hero hero-compact">
        <p className="hero-kicker">
          <Link to="/items" className="linklike" data-testid="back-to-items">
            ← Item directory
          </Link>
        </p>
        <h1 className="hero-title">
          {pretty ? (
            <>
              Everything about <span className="accent">{pretty}</span>
            </>
          ) : (
            <>Pick an item</>
          )}
        </h1>
        {pivot && (
          <p className="hero-pill" data-testid="item-pill">
            <span className="pulse-dot" aria-hidden="true" />
            {formatCount(pivot.tradeCount)} trades · {formatCount(pivot.craftCount)} made
            {pivot.tradeVolume ? ` · ${formatCount(pivot.tradeVolume)} currency moved` : ""}
          </p>
        )}
        {item && !pivot && error && (
          <p className="hero-pill hero-pill-muted" data-testid="item-error">
            item history unavailable right now
          </p>
        )}
      </section>

      {!item && (
        <section>
          <p className="empty-note" data-testid="item-missing">
            No item selected. Head to the{" "}
            <Link className="linklike" to="/items">
              item directory
            </Link>{" "}
            and pick one.
          </p>
        </section>
      )}

      {pivot && pivot.tradeCount === 0 && pivot.craftCount === 0 && (
        <section>
          <p className="empty-note" data-testid="item-empty">
            Nothing recorded for {pretty} yet — it has never been traded or crafted on this
            server.
          </p>
        </section>
      )}

      {pivot && pivot.tradeCount > 0 && (
        <section>
          <h2 className="section-title">
            Trades{" "}
            <span className="section-sub">
              (newest {Math.min(pivot.trades.length, EVENT_ROWS)}
              {pivot.tradeCount > pivot.trades.length
                ? ` of ${formatCount(pivot.tradeCount)}`
                : ""}
              )
            </span>
          </h2>
          <ul className="pivot-lines" data-testid="item-trades">
            {pivot.trades.slice(0, EVENT_ROWS).map((t, i) => (
              <li key={`t-${t.time}-${i}`} data-testid="item-trade-row">
                <span className="pivot-day">day {Math.floor(t.day)}</span>{" "}
                <strong>{t.seller || "someone"}</strong> sold {formatCount(t.quantity)}{" "}
                {pretty} to <strong>{t.buyer || "someone"}</strong>
                {pricePhrase(t.unitPrice, t.currency)}
              </li>
            ))}
          </ul>
        </section>
      )}

      {pivot && pivot.craftCount > 0 && (
        <section>
          <h2 className="section-title">
            Made{" "}
            <span className="section-sub">
              (newest {Math.min(pivot.crafts.length, EVENT_ROWS)}
              {pivot.craftCount > pivot.crafts.length
                ? ` of ${formatCount(pivot.craftCount)}`
                : ""}
              )
            </span>
          </h2>
          <ul className="pivot-lines" data-testid="item-crafts">
            {pivot.crafts.slice(0, EVENT_ROWS).map((c, i) => (
              <li key={`c-${c.time}-${i}`} data-testid="item-craft-row">
                <span className="pivot-day">day {Math.floor(c.day)}</span>{" "}
                <strong>{c.citizen || "someone"}</strong>{" "}
                {ACTION_VERBS[c.actionType] ?? "made"} {formatCount(c.quantity)} {pretty}
                {c.station && c.station !== "(hand)" ? ` at ${prettifyEcoName(c.station)}` : ""}
              </li>
            ))}
          </ul>
        </section>
      )}

      {pivot && pivot.warnings.length > 0 && (
        <section>
          <ul className="warn-list" data-testid="item-warnings">
            {pivot.warnings.map((w) => (
              <li key={w}>⚠ {w}</li>
            ))}
          </ul>
        </section>
      )}
    </Layout>
  )
}
