import { useEffect, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import Layout from "../components/Layout"
import { fetchCraftingAtlas, type CraftingAtlas } from "../lib/craftingApi"
import { formatCount, prettifyEcoName } from "../lib/format"

const ACTION_LABELS: Record<string, string> = {
  ItemCraftedAction: "crafted",
  HarvestOrHunt: "harvested",
  ChopTree: "trees felled",
  DigOrMine: "mined",
}

const TOP_N = 25

interface RankTableProps {
  rows: Array<[string, number]>
  filter: string
  emptyNote: string
  onPick: (name: string) => void
}

// Ranked bar list. With a filter active every match shows; without one the
// list cuts at TOP_N. Row clicks push the name into ?q= so views deep-link.
function RankTable({ rows, filter, emptyNote, onPick }: RankTableProps) {
  const needle = filter.trim().toLowerCase()
  const matches = needle
    ? rows.filter(([name]) => prettifyEcoName(name).toLowerCase().includes(needle))
    : rows.slice(0, TOP_N)
  const max = Math.max(...matches.map(([, count]) => count), 1)

  if (matches.length === 0) {
    return <p className="empty-note">{emptyNote}</p>
  }
  return (
    <ul className="rank-rows">
      {matches.map(([name, count]) => (
        <li key={name}>
          <button className="rank-row" onClick={() => onPick(prettifyEcoName(name))}>
            <span className="rank-name">{prettifyEcoName(name)}</span>
            <span className="rank-count">{formatCount(count)}</span>
            <span className="rank-bar" style={{ width: `${(count / max) * 100}%` }} />
          </button>
        </li>
      ))}
    </ul>
  )
}

// Top crafters ranks citizens by production count. Names arrive already
// resolved from the server's id→name join (or a "Citizen #<id>" fallback), so
// unlike items/stations they are shown verbatim — no Eco-id prettifying. This
// list doesn't feed the ?q filter, which only makes sense for items/stations.
function CrafterList({ rows }: { rows: Array<[string, number]> }) {
  const top = rows.slice(0, TOP_N)
  const max = Math.max(...top.map(([, count]) => count), 1)
  if (top.length === 0) {
    return <p className="empty-note">No citizen production recorded.</p>
  }
  return (
    <ul className="rank-rows">
      {top.map(([name, count]) => (
        <li key={name}>
          <div className="rank-row" data-testid="crafter-row">
            <span className="rank-name">{name}</span>
            <span className="rank-count">{formatCount(count)}</span>
            <span className="rank-bar" style={{ width: `${(count / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  )
}

export default function Crafting() {
  const [atlas, setAtlas] = useState<CraftingAtlas | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [params, setParams] = useSearchParams()
  const q = params.get("q") ?? ""

  useEffect(() => {
    const controller = new AbortController()
    fetchCraftingAtlas(controller.signal)
      .then(setAtlas)
      .catch((err) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err))
      })
    return () => controller.abort()
  }, [])

  const setQuery = (value: string) => {
    setParams(value ? { q: value } : {}, { replace: false })
  }

  return (
    <Layout>
      <section className="hero hero-compact">
        <p className="hero-kicker">Crafting atlas</p>
        <h1 className="hero-title">
          What the world is <span className="accent">making</span>
        </h1>
        {atlas && (
          <p className="hero-pill" data-testid="atlas-pill">
            <span className="pulse-dot" aria-hidden="true" />
            {formatCount(atlas.totalEvents)} production events ·{" "}
            {Object.entries(atlas.perActionCounts)
              .filter(([, count]) => count > 0)
              .map(([name, count]) => `${formatCount(count)} ${ACTION_LABELS[name] ?? name}`)
              .join(" · ")}
          </p>
        )}
        {!atlas && error && (
          <p className="hero-pill hero-pill-muted" data-testid="atlas-error">
            crafting atlas unavailable right now
          </p>
        )}
      </section>

      {atlas && (
        <>
          <section className="filter-row">
            <input
              className="filter-input"
              type="search"
              placeholder="Filter items and stations… (deep-linkable as ?q=)"
              value={q}
              onChange={(e) => setQuery(e.target.value)}
              data-testid="atlas-filter"
            />
            {q && (
              <button className="button" onClick={() => setQuery("")}>
                Clear
              </button>
            )}
          </section>

          <div className="atlas-columns">
            <section>
              <h2 className="section-title">Top items {q ? `matching "${q}"` : ""}</h2>
              <RankTable
                rows={atlas.byItem}
                filter={q}
                emptyNote="No items match."
                onPick={setQuery}
              />
            </section>
            <section>
              <h2 className="section-title">Top stations {q ? `matching "${q}"` : ""}</h2>
              <RankTable
                rows={atlas.byStation}
                filter={q}
                emptyNote="No stations match."
                onPick={setQuery}
              />
            </section>
          </div>

          <section>
            <h2 className="section-title">Top crafters</h2>
            <CrafterList rows={atlas.byCitizen} />
          </section>

          <section className="dir-cards">
            <Link className="dir-card" to="/economy" data-testid="link-economy">
              <h3>Economy →</h3>
              <p>The trading side of this production — trades per day, contracts, treasury.</p>
            </Link>
          </section>
        </>
      )}
    </Layout>
  )
}
