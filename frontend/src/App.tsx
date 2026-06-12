// Placeholder landing page. Deliberately dependency-light so the deploy
// rig stays trivial while the real design iterates.
export default function App() {
  return (
    <main className="page">
      <div className="card">
        <h1 className="wordmark">eco-app</h1>
        <p className="tagline">
          A live window into the <strong>Eco via Sirens</strong> game world.
          Meteor countdowns, economy, laws, species, and maps - a real site is
          growing here.
        </p>
        <div className="links">
          <a className="button" href="/preview">
            Live server card
          </a>
          <a className="button" href="/jobs/">
            Jobs tracker
          </a>
          <a
            className="button"
            href="https://store.steampowered.com/app/382310/Eco/"
          >
            Eco on Steam
          </a>
        </div>
        <p className="footer">
          Placeholder build. Unofficial fan project - Eco is a trademark of
          Strange Loop Games.
        </p>
      </div>
    </main>
  )
}
