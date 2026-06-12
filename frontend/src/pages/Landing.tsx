import { useEcoStatus } from "../hooks/useEcoStatus"
import Hero from "../components/Hero"
import MeteorBanner from "../components/MeteorBanner"
import StatGrid from "../components/StatGrid"
import Footer from "../components/Footer"

const STEAM_URL = "https://store.steampowered.com/app/382310/Eco/"

export default function Landing() {
  const { status, error, loading } = useEcoStatus()

  return (
    <div className="page">
      <header className="topbar">
        <span className="wordmark">eco-app</span>
        <nav className="topnav" aria-label="primary">
          <a href="/jobs/">Jobs tracker</a>
          <a href="/preview">Server card</a>
          {status?.server.discord && <a href={status.server.discord}>Discord</a>}
          <a href={STEAM_URL}>Steam</a>
        </nav>
      </header>

      <main className="content">
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
          {status?.server.discord && (
            <a className="button button-primary" href={status.server.discord}>
              Join the Discord
            </a>
          )}
          <a className="button" href={STEAM_URL}>
            Eco on Steam
          </a>
          <a className="button" href="/preview">
            Live server card
          </a>
          <a className="button" href="/jobs/">
            Jobs tracker
          </a>
        </section>
      </main>

      <Footer fetchedAtISO={status?.fetchedAtISO} />
    </div>
  )
}
