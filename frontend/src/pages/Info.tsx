import Layout from "../components/Layout"
import { useEcoStatus } from "../hooks/useEcoStatus"
import { safeHttpUrl } from "../lib/format"
import Hero from "../components/Hero"
import MeteorBanner from "../components/MeteorBanner"
import StatGrid from "../components/StatGrid"

const STEAM_URL = "https://store.steampowered.com/app/382310/Eco/"

// The live world snapshot: everything the old landing page carried, now one
// level down so the homepage stays a thin directory. Formerly "/server";
// renamed to "/info" in the eco-app#90 IA cleanup (the old path redirects here).
export default function Info() {
  const { status, error, loading } = useEcoStatus()
  const discordUrl = safeHttpUrl(status?.server.discord)

  return (
    <Layout fetchedAtISO={status?.fetchedAtISO}>
      <Hero status={status} error={error} />

      {loading && (
        <p className="loading" data-testid="loading">
          listening for the world…
        </p>
      )}

      {status && (
        <>
          <MeteorBanner cycle={status.cycle} />
          <StatGrid status={status} />
          <section aria-labelledby="online-players-heading">
            <h2 className="section-title" id="online-players-heading">
              Online now
            </h2>
            {status.players.onlineNames.length > 0 ? (
              <ul className="online-player-list" data-testid="online-player-list">
                {status.players.onlineNames.map((name) => (
                  <li className="mini-pill" key={name}>
                    {name}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-note" data-testid="online-player-empty">
                Nobody is online right now.
              </p>
            )}
          </section>
        </>
      )}

      <section className="cta-row">
        {discordUrl && (
          <a className="button button-discord" href={discordUrl}>
            Join the Discord
          </a>
        )}
        <a className="button" href={STEAM_URL}>
          Eco on Steam
        </a>
      </section>
    </Layout>
  )
}
