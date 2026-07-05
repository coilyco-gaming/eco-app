import { Link } from "react-router-dom"
import Layout from "../components/Layout"
import { useEcoStatus } from "../hooks/useEcoStatus"
import { useSocialPulse } from "../hooks/useSocialPulse"
import { useTradePulse } from "../hooks/useTradePulse"
import { formatCount, safeHttpUrl } from "../lib/format"

const STEAM_URL = "https://store.steampowered.com/app/382310/Eco/"

// The homepage is a thin directory: a short hero and one card per surface.
// The heavy live content lives on the subpages it points at.
export default function Home() {
  const { status } = useEcoStatus()
  const tradePulse = useTradePulse()
  const socialPulse = useSocialPulse()
  const discordUrl = safeHttpUrl(status?.server.discord)

  return (
    <Layout>
      <section className="hero hero-compact">
        <p className="hero-kicker">Eco via Sirens</p>
        <h1 className="hero-title">
          A live window into a <span className="accent">world worth saving</span>
        </h1>
        <p className="hero-tagline">
          Dashboards for the Eco via Sirens game server. Pick a surface — everything is one
          click from here.
        </p>
      </section>

      <section className="dir-cards" aria-label="site directory">
        <Link className="dir-card" to="/server" data-testid="dir-server">
          <h3>Server</h3>
          <p>Meteor countdown, players, world stats, and the economy at a glance.</p>
          {status && (
            <p className="dir-badges" data-testid="server-badges">
              {status.cycle.hasMeteor && (
                <span className="mini-pill">☄ {status.cycle.daysUntilMeteor}d to meteor</span>
              )}
              <span className="mini-pill">{formatCount(status.players.online)} online</span>
            </p>
          )}
        </Link>

        <Link className="dir-card" to="/jobs" data-testid="dir-jobs">
          <h3>Jobs</h3>
          <p>Who can make what — professions, specialties, and every player's skills.</p>
          {status && (
            <p className="dir-badges">
              <span className="mini-pill">{formatCount(status.players.total)} settlers</span>
            </p>
          )}
        </Link>

        <Link className="dir-card" to="/economy" data-testid="dir-economy">
          <h3>Economy</h3>
          <p>Trades per day, contracts, loans, wages, and the treasury.</p>
        </Link>

        <Link className="dir-card" to="/trade" data-testid="dir-trade">
          <h3>Trade &amp; logistics</h3>
          <p>Movers, price history, stores, and what to buy, sell, and ship next.</p>
          {tradePulse && (
            <p className="dir-badges" data-testid="trade-badges">
              <span className="mini-pill">{formatCount(tradePulse.markets)} markets</span>
              <span className="mini-pill">{formatCount(tradePulse.totalVolume)} volume</span>
            </p>
          )}
        </Link>

        <Link className="dir-card" to="/trades" data-testid="dir-trades">
          <h3>Trades ledger</h3>
          <p>Every individual trade — who sold what to whom, and price over time.</p>
        </Link>

        <Link className="dir-card" to="/crafting" data-testid="dir-crafting">
          <h3>Crafting atlas</h3>
          <p>What the world is making — top items and stations, deep-linkable.</p>
        </Link>

        <Link className="dir-card" to="/social" data-testid="dir-social">
          <h3>Social &amp; chat</h3>
          <p>Chat volume, the reputation graph, and new arrivals — names redacted.</p>
          {socialPulse && (
            <p className="dir-badges" data-testid="social-badges">
              <span className="mini-pill">{formatCount(socialPulse.chat)} messages</span>
              <span className="mini-pill">{formatCount(socialPulse.arrivals)} new</span>
            </p>
          )}
        </Link>

        <Link className="dir-card" to="/climate" data-testid="dir-climate">
          <h3>Climate</h3>
          <p>CO₂, temperature, sea level, and what the pollution is doing to the world.</p>
        </Link>

        <Link className="dir-card" to="/calculator" data-testid="dir-calculator">
          <h3>Calculator</h3>
          <p>Price your craft with Eco Gnome — optimal buy and sell prices from your recipes.</p>
        </Link>

        <div className="dir-card dir-card-static">
          <h3>Community</h3>
          <p>
            {discordUrl && (
              <>
                <a href={discordUrl}>Join the Discord</a>
                {" · "}
              </>
            )}
            <a href={STEAM_URL}>Eco on Steam</a>
          </p>
        </div>
      </section>
    </Layout>
  )
}
