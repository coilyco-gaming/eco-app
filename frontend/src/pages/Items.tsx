import { useEffect, useMemo, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import Layout from "../components/Layout"
import { fetchItemIndex, type ItemIndex } from "../lib/itemsApi"
import { formatCount, prettifyEcoName } from "../lib/format"

const LIST_ROWS = 200

// Directory of every item ever bought, sold, or crafted. Each row deep-links to
// the per-item pivot (/item?item=<id>). The list is ranked by total activity;
// the ?q= filter narrows by prettified name and is deep-linkable.
export default function Items() {
  const [index, setIndex] = useState<ItemIndex | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [params, setParams] = useSearchParams()
  const q = params.get("q") ?? ""

  useEffect(() => {
    const controller = new AbortController()
    fetchItemIndex(controller.signal)
      .then(setIndex)
      .catch((err) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err))
      })
    return () => controller.abort()
  }, [])

  const setQuery = (value: string) => {
    setParams(value ? { q: value } : {}, { replace: false })
  }

  const needle = q.trim().toLowerCase()
  const visible = useMemo(() => {
    if (!index) return []
    const matched = needle
      ? index.items.filter((r) => prettifyEcoName(r.item).toLowerCase().includes(needle))
      : index.items
    return matched.slice(0, LIST_ROWS)
  }, [index, needle])

  return (
    <Layout fetchedAtISO={index?.fetchedAtISO}>
      <section className="hero hero-compact">
        <p className="hero-kicker">Item directory</p>
        <h1 className="hero-title">
          Every <span className="accent">item</span> the world has touched
        </h1>
        {index && (
          <p className="hero-pill" data-testid="items-pill">
            <span className="pulse-dot" aria-hidden="true" />
            {formatCount(index.totalItems)} distinct items ever bought, sold, or crafted
          </p>
        )}
        {!index && error && (
          <p className="hero-pill hero-pill-muted" data-testid="items-error">
            item directory unavailable right now
          </p>
        )}
      </section>

      {index && index.totalItems === 0 && (
        <section>
          <p className="empty-note" data-testid="items-empty">
            No items recorded on this server yet. Early in a cycle this is normal — check back
            after a few days of trading and crafting.
          </p>
        </section>
      )}

      {index && index.totalItems > 0 && (
        <>
          <section className="filter-row">
            <input
              className="filter-input"
              type="search"
              placeholder="Filter items by name… (deep-linkable as ?q=)"
              value={q}
              onChange={(e) => setQuery(e.target.value)}
              data-testid="items-filter"
            />
            {q && (
              <button className="button" onClick={() => setQuery("")}>
                Clear
              </button>
            )}
          </section>

          <section>
            <h2 className="section-title">
              Items {q ? `matching "${q}"` : ""}{" "}
              <span className="section-sub">
                (showing {visible.length}
                {index.items.length > visible.length
                  ? ` of ${formatCount(index.items.length)}`
                  : ""}
                )
              </span>
            </h2>
            {visible.length === 0 ? (
              <p className="empty-note" data-testid="items-no-match">
                No items match.
              </p>
            ) : (
              <table className="ledger-table" data-testid="items-table">
                <thead>
                  <tr>
                    <th>Item</th>
                    <th className="num">Trades</th>
                    <th className="num">Trade volume</th>
                    <th className="num">Crafted</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((r) => (
                    <tr key={r.item} data-testid="item-row">
                      <td>
                        <Link className="linklike" to={`/item?item=${encodeURIComponent(r.item)}`}>
                          {prettifyEcoName(r.item)}
                        </Link>
                      </td>
                      <td className="num">{formatCount(r.tradeCount)}</td>
                      <td className="num">
                        {r.tradeVolume ? formatCount(r.tradeVolume) : "—"}
                      </td>
                      <td className="num">{r.craftCount ? formatCount(r.craftCount) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          {index.warnings.length > 0 && (
            <section>
              <ul className="warn-list" data-testid="items-warnings">
                {index.warnings.map((w) => (
                  <li key={w}>⚠ {w}</li>
                ))}
              </ul>
            </section>
          )}

          <section className="dir-cards">
            <Link className="dir-card" to="/trade" data-testid="link-trade">
              <h3>Trade →</h3>
              <p>The market and the full ledger — every individual trade, with price over time.</p>
            </Link>
            <Link className="dir-card" to="/crafting" data-testid="link-crafting">
              <h3>Crafting atlas →</h3>
              <p>What the world is making — top items, stations, and crafters.</p>
            </Link>
          </section>
        </>
      )}
    </Layout>
  )
}
