import type { EcoCycle } from "../lib/api"
import { meteorProgressPercent } from "../lib/format"

// The meteor is the heartbeat of an Eco cycle: the single shared deadline
// the whole server organizes around. It gets the loudest visual on the page.
export default function MeteorBanner({ cycle }: { cycle: EcoCycle }) {
  if (!cycle.hasMeteor) {
    return (
      <section className="meteor meteor-clear">
        <p className="meteor-count">The sky is clear</p>
        <p className="meteor-caption">
          No meteor this cycle - day {cycle.daysRunning} and counting.
        </p>
      </section>
    )
  }

  const pct = meteorProgressPercent(cycle.daysRunning, cycle.daysUntilMeteor)
  return (
    <section className="meteor" aria-label="meteor countdown">
      <p className="meteor-count" data-testid="meteor-count">
        ☄ {cycle.daysUntilMeteor} {cycle.daysUntilMeteor === 1 ? "day" : "days"} until the meteor
      </p>
      <div
        className="meteor-track"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="meteor-fill" style={{ width: `${pct}%` }} />
      </div>
      <p className="meteor-caption">
        Day {cycle.daysRunning} of the cycle · {pct}% of the way there
      </p>
    </section>
  )
}
