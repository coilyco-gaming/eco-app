import type { EcoStatus } from "../lib/api"
import { stripEcoMarkup } from "../lib/format"

interface HeroProps {
  status: EcoStatus | null
  error: string | null
}

export default function Hero({ status, error }: HeroProps) {
  // One heading tier, one intro line (eco-app#97): the live server description
  // *is* the heading, and the players pill is the single supporting line. The
  // former kicker, poetic title, and tagline stacked three tiers of prose.
  return (
    <section className="hero">
      <h1 className="hero-title">
        {status ? stripEcoMarkup(status.server.description) : "Live server snapshot"}
      </h1>
      {status && (
        <p className="hero-pill" data-testid="live-pill">
          <span className="pulse-dot" aria-hidden="true" />
          {status.players.online} online now · {status.players.total} settlers all-cycle
        </p>
      )}
      {!status && error && (
        <p className="hero-pill hero-pill-muted" data-testid="live-pill">
          live snapshot unavailable - the world spins on without us for a moment
        </p>
      )}
    </section>
  )
}
