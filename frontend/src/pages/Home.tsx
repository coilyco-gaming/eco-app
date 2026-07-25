import { Link } from "react-router-dom"
import Layout from "../components/Layout"
import { useCivicsPulse } from "../hooks/useCivicsPulse"
import { useClimatePulse } from "../hooks/useClimatePulse"
import { useCraftingPulse } from "../hooks/useCraftingPulse"
import { useEcoregionPulse } from "../hooks/useEcoregionPulse"
import { useEcoStatus } from "../hooks/useEcoStatus"
import { useTradePulse } from "../hooks/useTradePulse"
import { useTradesPulse } from "../hooks/useTradesPulse"
import { useWorldPulse } from "../hooks/useWorldPulse"
import { formatCount, prettifyEcoName, safeHttpUrl } from "../lib/format"

const STEAM_URL = "https://store.steampowered.com/app/382310/Eco/"
// Eco Gnome (MIT) is the crafting-cost calculator. It used to be its own
// /calculator page; eco-app#90 demoted it to this homepage card that links out
// to the gnome service. Roadmap (#40) self-hosts it at eco-gnome.coilysiren.me.
const ECO_GNOME_URL = "https://eco-gnome.coilysiren.me/"

// The homepage is a thin directory: a short hero and one card per surface.
// The heavy live content lives on the subpages it points at.
export default function Home() {
  const { status } = useEcoStatus()
  const tradePulse = useTradePulse()
  const civicsPulse = useCivicsPulse()
  const worldPulse = useWorldPulse()
  const tradesPulse = useTradesPulse()
  const craftingPulse = useCraftingPulse()
  const climatePulse = useClimatePulse()
  const ecoregionPulse = useEcoregionPulse()
  const discordUrl = safeHttpUrl(status?.server.discord)

  return (
    <Layout>
      {/* One heading + one intro line (eco-app#97). The poetic subtitle and
          kicker overline are gone. */}
      <section className="hero hero-compact">
        <h1 className="hero-title">Eco via Sirens</h1>
        <p className="hero-tagline">
          Intelligence and companionship for serious Eco servers. See what the world needs,
          where to trade, who can craft it, how civics changed, and what happened while you
          were away.
        </p>
      </section>

      <section className="dir-cards" aria-label="site directory">
        <Link className="dir-card" to="/info" data-testid="dir-info">
          <h3>Info</h3>
          <p>Meteor countdown, players, world stats, and the economy at a glance.</p>
          {status && (
            <p className="dir-badges" data-testid="info-badges">
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

        {/* Trade + the trades ledger are one surface now (eco-app#90). The
            badge strip fixes the old empty bubbles: markets falls back to a
            graceful 0 (the market plane is empty on servers that trade but have
            no priced markets), while volume and the trade count come from the
            ledger's own totalCurrencyVolume / totalTrades. */}
        <Link className="dir-card" to="/trade" data-testid="dir-trade">
          <h3>Trade &amp; logistics</h3>
          <p>
            Movers, price history, the full trade ledger, stores, and what to buy, sell, and ship
            next.
          </p>
          {(tradePulse || tradesPulse) && (
            <p className="dir-badges" data-testid="trade-badges">
              <span className="mini-pill">{formatCount(tradePulse?.markets ?? 0)} markets</span>
              {tradesPulse && (
                <>
                  <span className="mini-pill">{formatCount(tradesPulse.volume)} volume</span>
                  <span className="mini-pill">{formatCount(tradesPulse.trades)} trades</span>
                </>
              )}
              {tradesPulse?.topItem && (
                <span className="mini-pill">top: {prettifyEcoName(tradesPulse.topItem)}</span>
              )}
            </p>
          )}
        </Link>

        <Link className="dir-card" to="/crafting" data-testid="dir-crafting">
          <h3>Crafting atlas</h3>
          <p>What the world is making — top items and stations, deep-linkable.</p>
          {craftingPulse && (
            <p className="dir-badges" data-testid="crafting-badges">
              <span className="mini-pill">{formatCount(craftingPulse.crafts)} crafts</span>
              {craftingPulse.topItem && (
                <span className="mini-pill">top: {prettifyEcoName(craftingPulse.topItem)}</span>
              )}
            </p>
          )}
        </Link>

        <Link className="dir-card" to="/items" data-testid="dir-items">
          <h3>Item directory</h3>
          <p>Every item ever bought, sold, or crafted — click through to its full history.</p>
        </Link>

        {/* The recipe browse surface (eco-app#101): the bill-of-materials for
            every craftable, deep-linkable by product, profession, station, or
            ingredient. /recipe details are URL-only, reached from here. */}
        <Link className="dir-card" to="/recipes" data-testid="dir-recipes">
          <h3>Recipes</h3>
          <p>How everything is made — ingredients, station, profession, labor, and craft time.</p>
        </Link>

        {/* The /uses hub is the ONLY homepage card the whole use-case family
            gets (eco-app#99): the demand-side pages (what's in demand, buy/sell,
            arbitrage, shop-check) are URL-only, reached from the hub. */}
        <Link className="dir-card" to="/uses" data-testid="dir-uses">
          <h3>Use cases</h3>
          <p>Task-framed answers — what's in demand, where to buy or sell, arbitrage, shop pricing.</p>
        </Link>

        <Link className="dir-card" to="/civics" data-testid="dir-civics">
          <h3>Civics &amp; governance</h3>
          <p>Elections, turnout, demographics, and new settlements over time.</p>
          {civicsPulse && (
            <p className="dir-badges" data-testid="civics-badges">
              <span className="mini-pill">{formatCount(civicsPulse.events)} civic events</span>
              {civicsPulse.turnoutPct !== null && (
                <span className="mini-pill">{civicsPulse.turnoutPct}% turnout</span>
              )}
            </p>
          )}
        </Link>

        {/* Climate folded into the World card (eco-app#90): the map, biomes,
            ecoregions, mutation timeline, and the atmosphere all live on one
            page, so the badge strip carries world events, the busiest category,
            the dominant biome, and the climate headline together. */}
        <Link className="dir-card" to="/map" data-testid="dir-map">
          <h3>World</h3>
          <p>
            The live map, biome &amp; water mix, closest real-world ecoregions, the mutation
            timeline, and the climate — CO₂, temperature, and sea level.
          </p>
          {(worldPulse || ecoregionPulse || climatePulse) && (
            <p className="dir-badges" data-testid="world-badges">
              {worldPulse && (
                <span className="mini-pill">{formatCount(worldPulse.events)} events</span>
              )}
              {worldPulse?.topCategory && (
                <span className="mini-pill">{worldPulse.topCategory}</span>
              )}
              {ecoregionPulse?.topBiome && (
                <span className="mini-pill">{ecoregionPulse.topBiome}</span>
              )}
              {climatePulse && <span className="mini-pill">{climatePulse.status}</span>}
              {climatePulse?.co2Ppm != null && (
                <span className="mini-pill">{formatCount(climatePulse.co2Ppm)} ppm CO₂</span>
              )}
            </p>
          )}
        </Link>

        <a
          className="dir-card"
          href={ECO_GNOME_URL}
          target="_blank"
          rel="noreferrer"
          data-testid="dir-gnome"
        >
          <h3>Crafting calculator ↗</h3>
          <p>
            Price your craft with Eco Gnome (MIT) — optimal buy and sell prices from your
            professions and recipes. Opens the gnome service.
          </p>
        </a>

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
