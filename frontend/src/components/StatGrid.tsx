import type { EcoStatus } from "../lib/api"
import { formatCount } from "../lib/format"

interface Stat {
  label: string
  value: string
  detail?: string
}

export default function StatGrid({ status }: { status: EcoStatus }) {
  const stats: Stat[] = [
    {
      label: "Online now",
      value: formatCount(status.players.online),
      detail: `${formatCount(status.players.activeAndOnline)} active this week`,
    },
    {
      label: "Settlers",
      value: formatCount(status.players.total),
      detail: `peak ${formatCount(status.players.peakActive)} at once`,
    },
    { label: "Plants growing", value: formatCount(status.world.plants) },
    { label: "Laws in force", value: formatCount(status.world.laws) },
    {
      label: "Total culture",
      value: formatCount(status.world.totalCulture),
      // The server's own counter is unreliable per server; when it reads 0
      // against real milestone progress we show the milestone floor and say so
      // (eco-app#237).
      detail:
        status.world.totalCultureSource === "milestones"
          ? "at least — from milestones, the server reported 0"
          : undefined,
    },
    {
      label: "Economy",
      value: status.economy.description.split(",")[0] ?? status.economy.description,
      detail: status.economy.description.split(",").slice(1).join(",").trim() || undefined,
    },
    { label: "World", value: status.world.size, detail: status.cycle.gameSpeed.toLowerCase() + " speed" },
    { label: "Server", value: status.server.version.split(" ")[0] ?? "", detail: status.server.category },
  ]

  return (
    <section className="stats" aria-label="world snapshot">
      {stats.map((s) => (
        <div className="stat" key={s.label}>
          <p className="stat-value">{s.value}</p>
          <p className="stat-label">{s.label}</p>
          {s.detail && <p className="stat-detail">{s.detail}</p>}
        </div>
      ))}
    </section>
  )
}
