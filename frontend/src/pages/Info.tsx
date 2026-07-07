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
