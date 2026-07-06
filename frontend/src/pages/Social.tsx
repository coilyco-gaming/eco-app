import { useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"
import Layout from "../components/Layout"
import Loading from "../components/Loading"
import { fetchSocial, type ReputationEdge, type SocialSurface } from "../lib/socialApi"
import { formatCount, formatRelativeTime } from "../lib/format"

const TOP_N = 12
// Cap the reputation graph to the busiest nodes so the circular layout stays
// legible — the ranked giver/receiver lists below carry the long tail.
const MAX_GRAPH_NODES = 10

// Single-series bar chart of a per-in-game-day count series (chat volume, new
// arrivals). One hue, no legend — the section title names the series (dataviz:
// a single series needs no legend box). Hand-rolled SVG keeps the bundle lean
// and CSP trivial, matching the /trades PriceChart.
function VolumeChart({
  points,
  color,
  label,
  testid,
}: {
  points: Array<[number, number]>
  color: string
  label: string
  testid: string
}) {
  const width = 620
  const height = 150
  const pad = 28
  if (points.length === 0) {
    return <p className="empty-note">No {label.toLowerCase()} recorded yet.</p>
  }
  const days = points.map(([d]) => d)
  const counts = points.map(([, c]) => c)
  const minDay = Math.min(...days)
  const maxDay = Math.max(...days)
  const maxCount = Math.max(...counts, 1)
  const daySpan = maxDay - minDay || 1
  // Bar width scales to the day span; clamp so a sparse series still reads.
  const slot = (width - 2 * pad) / (daySpan + 1)
  const barW = Math.max(3, Math.min(28, slot * 0.7))

  const x = (d: number) => pad + ((d - minDay) / daySpan) * (width - 2 * pad)
  const y = (c: number) => height - pad - (c / maxCount) * (height - 2 * pad)

  return (
    <svg
      className="price-chart"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label={`${label} by in-game day`}
      data-testid={testid}
    >
      {points.map(([d, c]) => (
        <rect
          key={d}
          x={x(d) - barW / 2}
          y={y(c)}
          width={barW}
          height={height - pad - y(c)}
          rx={3}
          fill={color}
        >
          <title>
            Day {d}: {formatCount(c)} {label.toLowerCase()}
          </title>
        </rect>
      ))}
      <line
        x1={pad}
        y1={height - pad}
        x2={width - pad}
        y2={height - pad}
        stroke="var(--card-border)"
        strokeWidth="1"
      />
      <text x={pad} y={height - 6} className="axis-label">
        day {minDay}
      </text>
      <text x={width - pad} y={height - 6} textAnchor="end" className="axis-label">
        day {maxDay}
      </text>
      <text x={pad} y={16} className="axis-label">
        {formatCount(maxCount)}
      </text>
    </svg>
  )
}

// Directed "who reps whom" graph. Nodes are laid out on a circle; each edge is
// a curved arrow from giver to receiver, thickness scaled to the reputation
// moved. Node radius scales to reputation received. The ranked lists below are
// the table-view companion (dataviz accessibility pass), so the graph never
// carries meaning by geometry alone.
function ReputationGraph({ edges }: { edges: ReputationEdge[] }) {
  const size = 460
  const cx = size / 2
  const cy = size / 2
  const radius = size / 2 - 70

  const layout = useMemo(() => {
    const received = new Map<string, number>()
    const given = new Map<string, number>()
    for (const e of edges) {
      received.set(e.target, (received.get(e.target) ?? 0) + e.amount)
      given.set(e.source, (given.get(e.source) ?? 0) + e.amount)
    }
    const weight = (n: string) =>
      Math.abs(received.get(n) ?? 0) + Math.abs(given.get(n) ?? 0)
    const nodes = Array.from(new Set([...received.keys(), ...given.keys()]))
      .sort((a, b) => weight(b) - weight(a))
      .slice(0, MAX_GRAPH_NODES)
    const nodeSet = new Set(nodes)
    const pos = new Map<string, { x: number; y: number; angle: number }>()
    nodes.forEach((n, i) => {
      const angle = (i / nodes.length) * Math.PI * 2 - Math.PI / 2
      pos.set(n, { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius, angle })
    })
    const shown = edges.filter((e) => nodeSet.has(e.source) && nodeSet.has(e.target))
    const maxEdge = Math.max(...shown.map((e) => Math.abs(e.amount)), 1)
    const maxRecv = Math.max(...nodes.map((n) => Math.abs(received.get(n) ?? 0)), 1)
    return { nodes, pos, shown, maxEdge, received, maxRecv }
  }, [edges, cx, cy, radius])

  if (layout.nodes.length === 0) {
    return <p className="empty-note">No reputation transfers to graph yet.</p>
  }

  return (
    <svg
      className="rep-graph"
      viewBox={`0 0 ${size} ${size}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Reputation transfer graph — who reps whom"
      data-testid="rep-graph"
    >
      <defs>
        <marker
          id="rep-arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="7"
          markerHeight="7"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L10,5 L0,10 z" fill="var(--leaf-dim)" />
        </marker>
      </defs>
      {layout.shown.map((e) => {
        const a = layout.pos.get(e.source)!
        const b = layout.pos.get(e.target)!
        // Bow the edge toward the circle centre so reciprocal edges separate.
        const mx = (a.x + b.x) / 2
        const my = (a.y + b.y) / 2
        const qx = mx + (cx - mx) * 0.35
        const qy = my + (cy - my) * 0.35
        const w = 1 + (Math.abs(e.amount) / layout.maxEdge) * 6
        return (
          <path
            key={`${e.source}->${e.target}`}
            d={`M${a.x.toFixed(1)},${a.y.toFixed(1)} Q${qx.toFixed(1)},${qy.toFixed(1)} ${b.x.toFixed(1)},${b.y.toFixed(1)}`}
            fill="none"
            stroke="var(--leaf-dim)"
            strokeWidth={w}
            markerEnd="url(#rep-arrow)"
            data-testid="rep-edge"
          >
            <title>
              {e.source} → {e.target}: {e.amount > 0 ? "+" : ""}
              {formatCount(e.amount)} rep ({formatCount(e.count)}×)
            </title>
          </path>
        )
      })}
      {layout.nodes.map((n) => {
        const p = layout.pos.get(n)!
        const recv = Math.abs(layout.received.get(n) ?? 0)
        const r = 5 + (recv / layout.maxRecv) * 10
        // Push labels outward from the circle so they don't overlap the nodes.
        const lx = cx + Math.cos(p.angle) * (radius + 22)
        const ly = cy + Math.sin(p.angle) * (radius + 22)
        const anchor = Math.cos(p.angle) > 0.3 ? "start" : Math.cos(p.angle) < -0.3 ? "end" : "middle"
        return (
          <g key={n} data-testid="rep-node">
            <circle cx={p.x} cy={p.y} r={r} fill="var(--meteor)" stroke="var(--bg-deep)" strokeWidth="2">
              <title>
                {n}: {formatCount(recv)} reputation received
              </title>
            </circle>
            <text x={lx} y={ly + 4} textAnchor={anchor} className="rep-label">
              {n}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

interface RankListProps {
  rows: Array<[string, number]>
  emptyNote: string
}

// Ranked bar list — the table-view companion for the charts. Labels are already
// redacted handles from the server, shown verbatim.
function RankList({ rows, emptyNote }: RankListProps) {
  const top = rows.slice(0, TOP_N)
  const max = Math.max(...top.map(([, n]) => Math.abs(n)), 1)
  if (top.length === 0) {
    return <p className="empty-note">{emptyNote}</p>
  }
  return (
    <ul className="rank-rows">
      {top.map(([name, n]) => (
        <li key={name}>
          <div className="rank-row" data-testid="rank-row">
            <span className="rank-name">{name}</span>
            <span className="rank-count">{formatCount(n)}</span>
            <span className="rank-bar" style={{ width: `${(Math.abs(n) / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  )
}

export default function Social() {
  const [surface, setSurface] = useState<SocialSurface | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchSocial(controller.signal)
      .then(setSurface)
      .catch((err) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err))
      })
    return () => controller.abort()
  }, [])

  const isEmpty =
    surface !== null &&
    surface.totalChat === 0 &&
    surface.totalReputationTransfers === 0 &&
    surface.totalFirstLogins === 0 &&
    surface.totalPlayEvents === 0

  return (
    <Layout>
      <section className="hero hero-compact">
        <p className="hero-kicker">Social &amp; chat</p>
        <h1 className="hero-title">
          The <span className="accent">room</span>, not just the ledger
        </h1>
        {surface && !isEmpty && (
          <p className="hero-pill" data-testid="social-pill">
            <span className="pulse-dot" aria-hidden="true" />
            {formatCount(surface.totalChat)} messages · {formatCount(surface.totalReputationTransfers)}{" "}
            rep transfers · {formatCount(surface.totalFirstLogins)} new arrivals
          </p>
        )}
        {surface?.redacted && (
          <p className="redaction-note" data-testid="redaction-note">
            🔒 Names are redacted to stable handles and chat bodies are scrubbed of real names.
            This is a public surface — names in the clear are an operator-only mode.
          </p>
        )}
        {!surface && error && (
          <p className="hero-pill hero-pill-muted" data-testid="social-error">
            social surface unavailable right now
          </p>
        )}
      </section>

      {!surface && !error && <Loading label="Reading the room…" testid="social-loading" />}

      {surface && isEmpty && (
        <section>
          <p className="empty-note" data-testid="social-empty">
            No social activity recorded on this server yet. Early in a cycle this is normal — check
            back after a few days of play.
          </p>
        </section>
      )}

      {surface && !isEmpty && (
        <>
          <section>
            <h2 className="section-title">Chat volume over time</h2>
            <VolumeChart
              points={surface.chatByDay}
              color="var(--leaf)"
              label="Chat messages"
              testid="chat-volume-chart"
            />
          </section>

          <div className="atlas-columns">
            <section>
              <h2 className="section-title">Busiest channels</h2>
              <RankList rows={surface.chatByChannel} emptyNote="No chat channels recorded." />
            </section>
            <section>
              <h2 className="section-title">Top chatters</h2>
              <RankList rows={surface.topChatters} emptyNote="No chat authors recorded." />
            </section>
          </div>

          <section>
            <h2 className="section-title">
              Reputation graph{" "}
              <span className="section-sub">(who reps whom — top {MAX_GRAPH_NODES} by volume)</span>
            </h2>
            <div className="rep-layout">
              <ReputationGraph edges={surface.reputationEdges} />
              <div className="rep-lists">
                <div>
                  <h3 className="section-title-sm">Most-repped</h3>
                  <RankList
                    rows={surface.topReputationReceivers}
                    emptyNote="No reputation received yet."
                  />
                </div>
                <div>
                  <h3 className="section-title-sm">Top givers</h3>
                  <RankList
                    rows={surface.topReputationGivers}
                    emptyNote="No reputation given yet."
                  />
                </div>
              </div>
            </div>
          </section>

          {surface.firstLoginsByDay.length > 0 && (
            <section>
              <h2 className="section-title">
                New arrivals over time <span className="section-sub">(first logins per day)</span>
              </h2>
              <VolumeChart
                points={surface.firstLoginsByDay}
                color="var(--meteor)"
                label="New arrivals"
                testid="arrivals-chart"
              />
            </section>
          )}

          <section>
            <h2 className="section-title">
              Recent chat{" "}
              <span className="section-sub">
                (every message · {formatCount(surface.recentChat.length)}
                {surface.redacted ? " · redacted" : ""})
              </span>
            </h2>
            {surface.recentChat.length === 0 ? (
              <p className="empty-note">No chat samples available.</p>
            ) : (
              <table className="ledger-table" data-testid="chat-feed">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Author</th>
                    <th>Channel</th>
                    <th>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {surface.recentChat.map((m, i) => (
                    <tr key={`${m.timeS}-${i}`} data-testid="chat-row">
                      <td className="chat-when" title={`in-game day ${m.day}`}>
                        {formatRelativeTime(m.timeS, surface.latestTimeS)}
                      </td>
                      <td>{m.author}</td>
                      <td>{m.channel}</td>
                      <td className="chat-msg">{m.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          {surface.warnings.length > 0 && (
            <section>
              <ul className="warn-list" data-testid="social-warnings">
                {surface.warnings.map((w) => (
                  <li key={w}>⚠ {w}</li>
                ))}
              </ul>
            </section>
          )}

          <section className="dir-cards">
            <Link className="dir-card" to="/trade" data-testid="link-trade">
              <h3>Trade →</h3>
              <p>The material side — the market, the trade ledger, and money supply.</p>
            </Link>
            <Link className="dir-card" to="/jobs" data-testid="link-jobs">
              <h3>Jobs →</h3>
              <p>Who can make what — professions, specialties, and every settler's skills.</p>
            </Link>
          </section>
        </>
      )}
    </Layout>
  )
}
