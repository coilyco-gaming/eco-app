import { useEffect, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import Layout from "../components/Layout"
import { fetchItemPivot, type ItemFeedRow, type ItemPivot } from "../lib/itemsApi"
import { formatCount, formatDuration, formatRelative, prettifyEcoName } from "../lib/format"

// Maps the raw production action id to a past-tense verb for the feed lines.
const ACTION_VERBS: Record<string, string> = {
  ItemCraftedAction: "crafted",
  HarvestOrHunt: "harvested",
  ChopTree: "felled",
  DigOrMine: "mined",
}

const PAGE_SIZE = 50

type EventType = "all" | "craft" | "trade"

function fmtPrice(n: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(n)
}

function pricePhrase(unitPrice: number | null, currency: string): string {
  if (unitPrice === null || !currency) return ""
  return ` @ ${fmtPrice(unitPrice)} ${currency}`.trimEnd()
}

// A run of collapsed identical events reads as "(×N over 3 minutes)". A single
// event carries no run tail.
function runTail(row: ItemFeedRow): string {
  if (row.runCount <= 1) return ""
  const noun = row.kind === "craft" ? "crafts" : "trades"
  return ` (${formatCount(row.runCount)} ${noun} over ${formatDuration(row.spanSeconds)})`
}

// One feed row rendered as a single relative-time sentence. Compressed runs sum
// their quantity, so "crafted 100 Hewn Log" is the whole run, not one event.
function FeedLine({ row, item, now }: { row: ItemFeedRow; item: string; now: number }) {
  const when = formatRelative(row.time, now)
  if (row.kind === "craft") {
    const verb = ACTION_VERBS[row.actionType] ?? "made"
    const at =
      row.station && row.station !== "(hand)" ? ` at ${prettifyEcoName(row.station)}` : ""
    return (
      <li data-testid="item-feed-row">
        <span className="pivot-day">{when}</span>{" "}
        <strong>{row.actor || "someone"}</strong> {verb} {formatCount(row.quantity)} {item}
        {at}
        {runTail(row)}
      </li>
    )
  }
  return (
    <li data-testid="item-feed-row">
      <span className="pivot-day">{when}</span>{" "}
      <strong>{row.seller || "someone"}</strong> sold {formatCount(row.quantity)} {item} to{" "}
      <strong>{row.buyer || "someone"}</strong>
      {pricePhrase(row.unitPrice, row.currency)}
      {runTail(row)}
    </li>
  )
}

// Per-item pivot: an actionable summary (who makes it, what's for sale, who's
// buying) over a single reverse-chrono feed that interleaves crafts and trades,
// compresses repeats, and reads in relative time. Search / actor / type filters
// and the page are deep-linkable via query params (?q= ?actor= ?type= ?page=).
export default function Item() {
  const [params, setParams] = useSearchParams()
  const item = params.get("item") ?? ""
  const q = params.get("q") ?? ""
  const actor = params.get("actor") ?? ""
  const type = (params.get("type") ?? "all") as EventType
  const page = Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1)

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
  // loading gap rather than the previous item's data.
  const pivot = fetched && fetched.item === item ? fetched : null
  const error = erroredItem === item
  const pretty = item ? prettifyEcoName(item) : ""

  // Preserve the other params when one control changes; always reset to page 1
  // (except when the page itself changes).
  const update = (patch: Record<string, string>) => {
    const next: Record<string, string> = { item }
    if (q) next.q = q
    if (actor) next.actor = actor
    if (type !== "all") next.type = type
    if (page > 1) next.page = String(page)
    for (const [k, v] of Object.entries(patch)) {
      if (v) next[k] = v
      else delete next[k]
    }
    if (!("page" in patch)) delete next.page
    setParams(next, { replace: false })
  }

  const summary = pivot?.summary
  // Reference "now" for relative time: the world clock if we have it, else the
  // newest event on the page (formatRelative clamps future to "just now").
  // Plain consts — react-compiler memoizes; a manual useMemo here trips its
  // preserve-manual-memoization rule.
  const now = !pivot
    ? 0
    : pivot.worldClockS !== null
      ? pivot.worldClockS
      : pivot.feed.reduce((mx, r) => Math.max(mx, r.time), 0)

  // Distinct actors (crafters + both trade sides) for the actor dropdown.
  const actorSet = new Set<string>()
  for (const r of pivot?.feed ?? []) {
    for (const name of [r.actor, r.seller, r.buyer]) {
      if (name) actorSet.add(name)
    }
  }
  const actors = [...actorSet].sort((a, b) => a.localeCompare(b))

  const needle = q.trim().toLowerCase()
  const filtered = (pivot?.feed ?? []).filter((r) => {
    if (type !== "all" && r.kind !== type) return false
    if (actor && r.actor !== actor && r.seller !== actor && r.buyer !== actor) return false
    if (needle) {
      const hay = [r.actor, r.seller, r.buyer, r.station, r.currency, pretty]
        .join(" ")
        .toLowerCase()
      if (!hay.includes(needle)) return false
    }
    return true
  })

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const clampedPage = Math.min(page, totalPages)
  const pageRows = filtered.slice((clampedPage - 1) * PAGE_SIZE, clampedPage * PAGE_SIZE)

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
            {formatCount(pivot.tradeCount)} trades · {formatCount(pivot.craftQuantity)} made
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

      {/* Actionable summary — should I craft it, where do I buy it, who buys it. */}
      {pivot && summary && (pivot.tradeCount > 0 || pivot.craftCount > 0) && (
        <section className="summary-cols" data-testid="item-summary">
          <div>
            <h2 className="section-title">Who can make it</h2>
            {summary.crafters.length === 0 ? (
              <p className="empty-note">No recorded crafters.</p>
            ) : (
              <ul className="rank-rows" data-testid="item-crafters">
                {summary.crafters.map((c) => {
                  const max = Math.max(...summary.crafters.map((x) => x.quantity), 1)
                  return (
                    <li key={c.name}>
                      <button className="rank-row" onClick={() => update({ actor: c.name, type: "craft" })}>
                        <span className="rank-name">{c.name}</span>
                        <span className="rank-count">
                          {formatCount(c.quantity)} made · {formatCount(c.events)} craft
                          {c.events === 1 ? "" : "s"}
                        </span>
                        <span className="rank-bar" style={{ width: `${(c.quantity / max) * 100}%` }} />
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
          <div>
            <h2 className="section-title">
              Available now{" "}
              <span className="section-sub">
                ({summary.live ? "live shelf" : "history-derived"})
              </span>
            </h2>
            {summary.supply.offers.length === 0 ? (
              <p className="empty-note">No open sell offers.</p>
            ) : (
              <>
                <p className="hero-pill" data-testid="item-supply-total">
                  {formatCount(summary.supply.totalQuantity)}
                  {summary.supply.capped ? "+" : ""} in stock across{" "}
                  {formatCount(summary.supply.storeCount)} store
                  {summary.supply.storeCount === 1 ? "" : "s"}
                </p>
                <ul className="rank-rows" data-testid="item-supply">
                  {summary.supply.offers.map((o, i) => (
                    <li key={`${o.store}-${i}`}>
                      <div className="rank-row">
                        <span className="rank-name">{o.store}</span>
                        <span className="rank-count">
                          {o.price !== null ? `${fmtPrice(o.price)} ${o.currency}` : "—"}
                          {o.quantity !== null ? ` · ${formatCount(o.quantity)} in stock` : ""}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
          <div>
            <h2 className="section-title">Who is buying</h2>
            {summary.demand.offers.length === 0 ? (
              <p className="empty-note">No open buy orders.</p>
            ) : (
              <>
                <p className="hero-pill" data-testid="item-demand-total">
                  {formatCount(summary.demand.totalQuantity)}
                  {summary.demand.capped ? "+" : ""} wanted across{" "}
                  {formatCount(summary.demand.storeCount)} buyer
                  {summary.demand.storeCount === 1 ? "" : "s"}
                </p>
                <ul className="rank-rows" data-testid="item-demand">
                  {summary.demand.offers.map((o, i) => (
                    <li key={`${o.store}-${i}`}>
                      <div className="rank-row">
                        <span className="rank-name">{o.owner || o.store}</span>
                        <span className="rank-count">
                          {o.price !== null ? `${fmtPrice(o.price)} ${o.currency}` : "—"}
                          {o.quantity !== null ? ` · wants ${formatCount(o.quantity)}` : ""}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        </section>
      )}

      {/* Merged reverse-chrono feed with search / actor / type filters + paging. */}
      {pivot && pivot.feed.length > 0 && (
        <section>
          <div className="filter-row" data-testid="item-filters">
            <input
              className="filter-input"
              type="search"
              placeholder="Search the feed by name, station, currency… (deep-linkable as ?q=)"
              value={q}
              onChange={(e) => update({ q: e.target.value })}
              data-testid="item-filter"
            />
            <select
              className="filter-select"
              value={actor}
              onChange={(e) => update({ actor: e.target.value })}
              data-testid="item-actor-filter"
              aria-label="Filter by actor"
            >
              <option value="">Anyone</option>
              {actors.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
            <select
              className="filter-select"
              value={type}
              onChange={(e) => update({ type: e.target.value })}
              data-testid="item-type-filter"
              aria-label="Filter by event type"
            >
              <option value="all">All events</option>
              <option value="craft">Crafts</option>
              <option value="trade">Trades</option>
            </select>
            {(q || actor || type !== "all") && (
              <button
                className="button"
                onClick={() => update({ q: "", actor: "", type: "" })}
                data-testid="item-clear"
              >
                Clear
              </button>
            )}
          </div>

          <h2 className="section-title">
            Timeline{" "}
            <span className="section-sub">
              ({formatCount(filtered.length)} event{filtered.length === 1 ? "" : "s"}
              {pivot.feedTruncated ? "+, compressed" : ", compressed"})
            </span>
          </h2>

          {pageRows.length === 0 ? (
            <p className="empty-note" data-testid="item-no-match">
              No events match these filters.
            </p>
          ) : (
            <ul className="pivot-lines" data-testid="item-feed">
              {pageRows.map((row, i) => (
                <FeedLine key={`${row.kind}-${row.time}-${i}`} row={row} item={pretty} now={now} />
              ))}
            </ul>
          )}

          {totalPages > 1 && (
            <div className="pager" data-testid="item-pager">
              <button
                className="button"
                disabled={clampedPage <= 1}
                onClick={() => update({ page: String(clampedPage - 1) })}
                data-testid="item-prev"
              >
                ← Newer
              </button>
              <span className="pager-status">
                Page {clampedPage} of {totalPages}
              </span>
              <button
                className="button"
                disabled={clampedPage >= totalPages}
                onClick={() => update({ page: String(clampedPage + 1) })}
                data-testid="item-next"
              >
                Older →
              </button>
            </div>
          )}
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
