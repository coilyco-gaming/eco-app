import type { EcoStatus } from "../lib/api"
import { stripEcoMarkup } from "../lib/format"

interface HeroProps {
  status: EcoStatus | null
  error: string | null
}

export default function Hero({ status, error }: HeroProps) {
  return (
    <section className="hero">
      <p className="hero-kicker">Eco via Sirens</p>
      <h1 className="hero-title">
        A live window into a <span className="accent">world worth saving</span>
      </h1>
      <p className="hero-tagline">
        {status
          ? stripEcoMarkup(status.server.description)
          : "Meteor countdowns, economy, laws, species, and maps from the Eco via Sirens game server."}
      </p>
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
