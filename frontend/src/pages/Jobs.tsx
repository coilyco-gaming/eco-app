import { useEffect, useMemo, useState } from "react"
import type { ReactNode } from "react"
import ItemLink from "../components/ItemLink"
import Layout from "../components/Layout"
import { useJobsData } from "../hooks/useJobsData"
import { fetchLogistics, type GapReason, type LogisticsBoard } from "../lib/logisticsApi"
import { fetchMarket, type MarketIntelligence } from "../lib/marketApi"
import { formatCount, prettifyEcoName } from "../lib/format"
import { fetchRecipeIndexWithCost, type RecipeIndexWithCost } from "../lib/recipesApi"
import { fetchTradesLedger, type TradesLedger } from "../lib/tradesApi"
import type { PlayerRow, ProfessionStat, SpecialtyStat } from "../lib/jobsApi"
import {
  fetchProgressionHistory,
  KIND_LABELS,
  TREND_ORDER,
  type CitizenTrajectory,
  type ProgressionHistory,
} from "../lib/progressionApi"

// Survivalist and Self Improvement are the universal starter skills — every
// citizen has them, so they carry no signal and only clutter the roster
// (eco-app#94). We filter them out of every jobs surface (professions,
// specialties, per-player skill lists, and the progression rank lists) in one
// place here. Matching on the prettified, whitespace-collapsed name catches
// both the jobs API's display names ("Self Improvement") and the progression
// endpoint's raw Eco ids ("SelfImprovement", "SurvivalistSkill").
const UNIVERSAL_SKILLS = new Set(["self improvement", "survivalist"])
const VALUE_ROWS = 5
const LIQUIDITY_FLOOR = 100

const GAP: Record<GapReason, { glyph: string; label: string; color: string }> = {
  no_supply: { glyph: "✖", label: "no supply", color: "var(--meteor)" },
  thin_supply: { glyph: "◐", label: "thin supply", color: "var(--meteor-deep)" },
  overpriced: { glyph: "▲", label: "over-priced", color: "var(--ink-faint)" },
}

function fmtPrice(n: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(n)
}

function isUniversalSkill(name: string): boolean {
  const norm = prettifyEcoName(name)
    .toLowerCase()
    .replace(/\bskill\b/g, "")
    .replace(/\s+/g, " ")
    .trim()
  return UNIVERSAL_SKILLS.has(norm)
}

interface RankRow {
  key: string
  name: string
  count: number
  note?: ReactNode
}

interface ValueRow {
  key: string
  item: string
  name: string
  score: number
  note: ReactNode
}

type RankedRow = RankRow | ValueRow

interface ProfessionValueBoard {
  key: string
  label: string
  rows: ValueRow[]
}

function ProfessionCard({ stat }: { stat: ProfessionStat }) {
  const [open, setOpen] = useState(false)
  return (
    <li className={`card card-tight${stat.total === 0 ? " dim" : ""}`}>
      <button className="prof-btn" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <span>{stat.profession}</span>
        <span className="count">
          ( {stat.active} / {stat.total} )
        </span>
      </button>
      {open && (
        <div className="detail">
          {stat.players.length > 0 ? (
            <ul className="rows">
              {stat.players.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          ) : (
            <p className="empty-note">No players with specialties in this profession.</p>
          )}
        </div>
      )}
    </li>
  )
}

function SpecialtyCard({ stat }: { stat: SpecialtyStat }) {
  return (
    <li className={`card${stat.active === 0 ? " dim" : ""}`}>
      <h3 className="card-title">
        {stat.specialty}
        <span className="count">
          ( {stat.active} / {stat.total} )
        </span>
      </h3>
      <p className="kicker">{stat.profession}</p>
      <ul className="rows">
        {stat.holders.map((h) => (
          <li key={h.player} className={h.active ? undefined : "faded"}>
            <span>{h.player}</span>
            <span className="lvl">lvl {h.level}</span>
          </li>
        ))}
      </ul>
    </li>
  )
}

// A player card, enriched with a "how they got here" history lane when the
// progression surface has a matching trajectory (eco-app#64). The current-state
// specialties come from the jobs API; the expandable timeline is the history.
function PlayerCard({
  player,
  trajectory,
}: {
  player: PlayerRow
  trajectory?: CitizenTrajectory
}) {
  const [open, setOpen] = useState(false)
  return (
    <li className={`card${player.active ? "" : " dim"}`}>
      <h3 className="card-title">
        {player.name}
        {player.active ? (
          <span className="pill pill-active">active</span>
        ) : (
          <span className="pill pill-inactive">inactive</span>
        )}
      </h3>
      <ul className="rows">
        {player.specialties.map((s) => (
          <li key={s.specialty}>
            <span>{s.specialty}</span>
            <span className="lvl">lvl {s.level}</span>
          </li>
        ))}
      </ul>
      {trajectory && trajectory.timeline.length > 0 && (
        <>
          <button
            className="prof-btn prof-btn-sub"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            data-testid="player-history-toggle"
          >
            <span>How they got here</span>
            <span className="count">{formatCount(trajectory.levelUpCount)} level-ups</span>
          </button>
          {open && (
            <ul className="prog-timeline" data-testid="player-history">
              {trajectory.timeline.map((ev, i) => (
                <li key={`${ev.time}-${i}`}>
                  <span className="prog-day">day {ev.day}</span>
                  <span className="prog-what">
                    {KIND_LABELS[ev.kind] ?? ev.kind}
                    {ev.skill ? `: ${ev.pretty}` : ""}
                    {ev.level !== null ? ` (lvl ${Math.round(ev.level)})` : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </li>
  )
}

// One small-multiple sparkline of a single progression trend series (events of
// one kind per in-game day). Small multiples — one single-hue chart per kind —
// deliberately sidestep the multi-series categorical-color problem: every panel
// reads on the same --leaf hue, and its title names the single series (no legend
// box needed). Folded into /jobs from the former /progression page (eco-app#90).
function TrendSparkline({
  label,
  points,
}: {
  label: string
  points: Array<[number, number]>
}) {
  const width = 300
  const height = 96
  const pad = 16
  const total = points.reduce((sum, [, c]) => sum + c, 0)

  let body
  if (points.length < 2) {
    // A single day (or none) can't draw a line; show the headline count instead.
    body = (
      <p className="prog-trend-single" data-testid="trend-single">
        {formatCount(total)} total{points.length === 1 ? ` · day ${points[0][0]}` : ""}
      </p>
    )
  } else {
    const days = points.map(([d]) => d)
    const counts = points.map(([, c]) => c)
    const minDay = Math.min(...days)
    const maxDay = Math.max(...days)
    const maxCount = Math.max(...counts)
    const daySpan = maxDay - minDay || 1
    const countSpan = maxCount || 1
    const x = (d: number) => pad + ((d - minDay) / daySpan) * (width - 2 * pad)
    const y = (c: number) => height - pad - (c / countSpan) * (height - 2 * pad)
    const line = points.map(([d, c]) => `${x(d).toFixed(1)},${y(c).toFixed(1)}`).join(" ")
    const area = `${x(minDay).toFixed(1)},${(height - pad).toFixed(1)} ${line} ${x(
      maxDay,
    ).toFixed(1)},${(height - pad).toFixed(1)}`
    body = (
      <svg
        className="prog-trend-chart"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`${KIND_LABELS[label] ?? label} per in-game day`}
        data-testid="trend-chart"
      >
        <polygon points={area} fill="var(--leaf-wash)" stroke="none" />
        <polyline points={line} fill="none" stroke="var(--leaf)" strokeWidth="2" />
        <text x={pad} y={height - 4} className="axis-label">
          day {minDay}
        </text>
        <text x={width - pad} y={height - 4} textAnchor="end" className="axis-label">
          day {maxDay}
        </text>
        <text x={pad} y={14} className="axis-label">
          peak {formatCount(maxCount)}
        </text>
      </svg>
    )
  }

  return (
    <div className="prog-trend" data-testid="trend-panel">
      <div className="prog-trend-title">
        {KIND_LABELS[label] ?? label}
        <span className="prog-trend-total">{formatCount(total)}</span>
      </div>
      {body}
    </div>
  )
}

// Ranked bar list of [name, count] pairs. `pretty` prettifies Eco skill ids;
// citizen-name lists (already resolved server-side) pass pretty={false}.
function RankList({
  rows,
  emptyNote,
  pretty = true,
  formatValue = formatCount,
}: {
  rows: RankedRow[]
  emptyNote: string
  pretty?: boolean
  formatValue?: (n: number) => string
}) {
  const top = rows.slice(0, 15)
  const valueFor = (row: RankedRow) => ("count" in row ? row.count : row.score)
  const max = Math.max(...top.map(valueFor), 1)
  if (top.length === 0) {
    return <p className="empty-note">{emptyNote}</p>
  }
  return (
    <ul className="rank-rows">
      {top.map((row) => (
        <li key={row.key}>
          <div className="rank-row" data-testid="rank-row">
            {"item" in row ? (
              <ItemLink className="rank-name linklike" item={row.item}>
                {row.name}
              </ItemLink>
            ) : (
              <span className="rank-name">{pretty ? prettifyEcoName(row.name) : row.name}</span>
            )}
            <span className="rank-count">{formatValue(valueFor(row))}</span>
            <span className="rank-bar" style={{ width: `${(valueFor(row) / max) * 100}%` }} />
          </div>
          {row.note && <p className="section-sub">{row.note}</p>}
        </li>
      ))}
    </ul>
  )
}

function ValueTag({ reason }: { reason: GapReason }) {
  const tag = GAP[reason]
  return (
    <span className="gap-tag" style={{ color: tag.color }} data-testid="value-tag">
      <span aria-hidden="true">{tag.glyph}</span> {tag.label}
    </span>
  )
}

function makeRankRow(
  key: string,
  name: string,
  count: number,
  note?: ReactNode,
): RankRow {
  return { key, name, count, note }
}

export default function Jobs() {
  const { data, error, loading } = useJobsData()
  // Progression is the temporal layer of this page (eco-app#90): the current
  // roster shows who does what now, progression shows how they got there. It is
  // a best-effort enrichment — a failure leaves the current-state tables exactly
  // as they were before this surface existed, so we swallow errors.
  const [progression, setProgression] = useState<ProgressionHistory | null>(null)
  const [recipeIndex, setRecipeIndex] = useState<RecipeIndexWithCost | null>(null)
  const [logistics, setLogistics] = useState<LogisticsBoard | null>(null)
  const [market, setMarket] = useState<MarketIntelligence | null>(null)
  const [trades, setTrades] = useState<TradesLedger | null>(null)
  const [valueLoaded, setValueLoaded] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    fetchProgressionHistory(controller.signal)
      .then(setProgression)
      .catch(() => {
        /* non-fatal: the trajectory layer just doesn't render */
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller
    const requests = [
      fetchRecipeIndexWithCost(signal).then(
        (value) => {
          if (!signal.aborted) setRecipeIndex(value)
        },
        () => {
          if (!signal.aborted) setRecipeIndex(null)
        },
      ),
      fetchLogistics(signal).then(
        (value) => {
          if (!signal.aborted) setLogistics(value)
        },
        () => {
          if (!signal.aborted) setLogistics(null)
        },
      ),
      fetchMarket(signal).then(
        (value) => {
          if (!signal.aborted) setMarket(value)
        },
        () => {
          if (!signal.aborted) setMarket(null)
        },
      ),
      fetchTradesLedger(signal).then(
        (value) => {
          if (!signal.aborted) setTrades(value)
        },
        () => {
          if (!signal.aborted) setTrades(null)
        },
      ),
    ]
    Promise.all(requests).finally(() => {
      if (!signal.aborted) setValueLoaded(true)
    })

    return () => controller.abort()
  }, [])

  const trajectoryByName = useMemo(() => {
    const map = new Map<string, CitizenTrajectory>()
    for (const c of progression?.citizens ?? []) map.set(c.name, c)
    return map
  }, [progression])

  const trendPanels = useMemo(() => {
    if (!progression) return []
    return TREND_ORDER.filter((kind) => (progression.trends[kind]?.length ?? 0) > 0).map(
      (kind) => ({ kind, points: progression.trends[kind] }),
    )
  }, [progression])

  const hasHistory = (progression?.totalEvents ?? 0) > 0

  // Drop the universal starter skills from every current-state surface
  // (eco-app#94). Professions and specialties filter by name; players keep
  // their card but shed the two universal rows.
  const professions = useMemo(
    () => (data?.professions ?? []).filter((s) => !isUniversalSkill(s.profession)),
    [data],
  )
  const specialties = useMemo(
    () => (data?.specialties ?? []).filter((s) => !isUniversalSkill(s.specialty)),
    [data],
  )
  const players = useMemo(
    () =>
      (data?.players ?? []).map((p) => ({
        ...p,
        specialties: p.specialties.filter((s) => !isUniversalSkill(s.specialty)),
      })),
    [data],
  )

  const valueBoards = useMemo<ProfessionValueBoard[] | null>(() => {
    if (!recipeIndex || !logistics || !market || !trades) return null

    const marketMedians = new Map(market.markets.map((m) => [m.item, m.medianPrice] as const))
    const gaps = new Map(logistics.supplyGaps.map((g) => [g.item, g] as const))
    const liquidity = new Map(trades.byItem.map(([item, , volume]) => [item, volume] as const))
    const recipesByName = new Map(recipeIndex.recipes.map((r) => [r.name, r] as const))

    const boards = recipeIndex.skills
      .map((skill) => {
        const bestByItem = new Map<string, ValueRow>()
        for (const recipeName of recipeIndex.bySkill[skill.name] ?? []) {
          const recipe = recipesByName.get(recipeName)
          if (!recipe?.cost?.complete || recipe.cost.perUnitCost == null) continue
          const item = recipe.product.item
          const gap = gaps.get(item)
          const median = marketMedians.get(item)
          const traded = liquidity.get(item) ?? 0
          if (!gap || median == null || traded < LIQUIDITY_FLOOR || gap.demandQty <= 0) continue
          const margin = median - recipe.cost.perUnitCost
          if (margin <= 0) continue
          const boost = gap.reason === "no_supply" ? 1.5 : gap.reason === "thin_supply" ? 1.25 : 1.0
          const score = margin * gap.demandQty * boost
          const note = (
            <>
              <ValueTag reason={gap.reason} />{" "}
              <span>
                margin {fmtPrice(margin)} · {formatCount(gap.demandQty)} wanted ·{" "}
                {formatCount(traded)} traded volume
              </span>
            </>
          )
          const current = bestByItem.get(item)
          if (!current || score > current.score) {
            bestByItem.set(item, {
              key: recipe.name,
              item,
              name: recipe.product.displayName,
              score,
              note,
            })
          }
        }

        const rows = [...bestByItem.values()].sort((a, b) => b.score - a.score).slice(0, VALUE_ROWS)
        return rows.length > 0
          ? {
              key: skill.name,
              label: skill.displayName || prettifyEcoName(skill.name),
              rows,
            }
          : null
      })
      .filter((board): board is ProfessionValueBoard => board !== null)
      .sort((a, b) => (b.rows[0]?.score ?? 0) - (a.rows[0]?.score ?? 0) || a.label.localeCompare(b.label))

    return boards
  }, [recipeIndex, logistics, market, trades])

  // Same exclusion for the progression rank lists (name-keyed leaderboards).
  const dropUniversal = (rows: Array<[string, number]>) =>
    rows.filter(([name]) => !isUniversalSkill(name))

  return (
    <Layout>
      {data?.mockData && (
        <div className="mock-banner" data-testid="mock-banner">
          ⚠️ MOCK DATA — every player, skill, and count on this page is fabricated. Set the{" "}
          <code>UPSTREAM_URL</code> env var on the service to pull real data. ⚠️
        </div>
      )}

      <section className="intro">
        <p>
          Who does what on the Eco server and how they got there — the history up top, the current
          roster below. "Active" means logged in within the last week.
        </p>
      </section>

      {/* The server-wide trajectory layer: how the current roster below formed.
          Moved above the current-state tables so the history reads first
          (eco-app#94); folded in from the former /progression page (eco-app#90). */}
      {hasHistory && (
        <section className="jobs-progression" data-testid="jobs-progression">
          <h2 className="section-title">
            How the world got here{" "}
            <span className="section-sub">
              ({formatCount(progression!.totalEvents)} recorded skill events —{" "}
              {formatCount(progression!.citizens.length)} citizens)
            </span>
          </h2>

          {trendPanels.length > 0 && (
            <div className="prog-trend-grid" data-testid="trend-grid">
              {trendPanels.map(({ kind, points }) => (
                <TrendSparkline key={kind} label={kind} points={points} />
              ))}
            </div>
          )}

          <div className="atlas-columns">
            <div>
              <h3 className="subsection-title">Most-gained specialties</h3>
              <RankList
                rows={dropUniversal(progression!.bySpecialty).map(([name, count]) =>
                  makeRankRow(name, name, count),
                )}
                emptyNote="No specialties gained yet."
              />
            </div>
            <div>
              <h3 className="subsection-title">Busiest levelers</h3>
              <RankList
                rows={progression!.topLevelers.map(([name, count]) => makeRankRow(name, name, count))}
                emptyNote="No level-ups recorded yet."
                pretty={false}
              />
            </div>
          </div>

          {dropUniversal(progression!.classCompletions).length > 0 && (
            <>
              <h3 className="subsection-title">Classes completed</h3>
              <RankList
                rows={dropUniversal(progression!.classCompletions).map(([name, count]) =>
                  makeRankRow(name, name, count),
                )}
                emptyNote="No classes completed yet."
              />
            </>
          )}

          {progression!.warnings.length > 0 && (
            <ul className="warn-list" data-testid="progression-warnings">
              {progression!.warnings.map((w) => (
                <li key={w}>⚠ {w}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      {loading && (
        <p className="loading" data-testid="loading">
          tallying the workshops…
        </p>
      )}

      {error && !data && (
        <p className="loading" data-testid="jobs-error">
          jobs data unavailable right now — the world spins on without us for a moment
        </p>
      )}

      {data && (
        <>
          <section data-testid="jobs-value">
            <h2 className="section-title">
              Most valuable to craft{" "}
              <span className="section-sub">(per profession, true margin × demand)</span>
            </h2>
            {!valueLoaded ? (
              <p className="empty-note" data-testid="jobs-value-loading">
                tallying craft margins…
              </p>
            ) : valueBoards === null ? (
              <p className="empty-note" data-testid="jobs-value-empty">
                Need recipes, market medians, logistics gaps, and trade volume to rank crafts.
              </p>
            ) : valueBoards.length === 0 ? (
              <p className="empty-note" data-testid="jobs-value-empty">
                No liquid supply-gap crafts yet.
              </p>
            ) : (
              <div className="value-boards" data-testid="jobs-value-boards">
                {valueBoards.map((board) => (
                  <section className="value-board" key={board.key} data-testid="value-board">
                    <h3 className="subsection-title">{board.label}</h3>
                    <RankList
                      rows={board.rows}
                      emptyNote={`No liquid supply-gap crafts for ${board.label} yet.`}
                      pretty={false}
                      formatValue={fmtPrice}
                    />
                  </section>
                ))}
              </div>
            )}
          </section>

          <section>
            <h2 className="section-title">Professions</h2>
            <ul className="cards">
              {professions.map((s) => (
                <ProfessionCard key={s.profession} stat={s} />
              ))}
            </ul>
          </section>

          <section>
            <h2 className="section-title">Specialties</h2>
            <ul className="cards">
              {specialties.map((s) => (
                <SpecialtyCard key={s.specialty} stat={s} />
              ))}
            </ul>
          </section>

          <section>
            <h2 className="section-title">
              Players{" "}
              {hasHistory && (
                <span className="section-sub">(expand a player for their skill timeline)</span>
              )}
            </h2>
            <ul className="cards">
              {players.map((p) => (
                <PlayerCard key={p.name} player={p} trajectory={trajectoryByName.get(p.name)} />
              ))}
            </ul>
          </section>
        </>
      )}
    </Layout>
  )
}
