import Layout from "../components/Layout"

// Eco Gnome is an MIT-licensed price calculator for Eco, by the Eco-Gnome
// project (https://github.com/Eco-Gnome/eco-gnome-website). This surface is
// the eco-app seam it slots into: today it points players at the upstream
// public instance; the roadmap (issue #40) is a self-hosted instance on
// eco-app.coilysiren.me fed by Sirens' own recipe/skill data via the
// DataExporter mod, so the pricing matches this server, not vanilla Eco.
// The self-host deploy slot (Blazor Server + Postgres, pinned upstream image)
// now lives in coilyco-bridge/deploy/services/eco-gnome and serves at
// eco-gnome.coilysiren.me once rolled out; scoped in docs/calculator.md. Not
// built from scratch by design.
const ECO_GNOME_URL = "https://eco-gnome.com"
const ECO_GNOME_REPO = "https://github.com/Eco-Gnome/eco-gnome-website"
const ECO_GNOME_MOD = "https://github.com/Eco-Gnome/eco-gnome-mod"

export default function Calculator() {
  return (
    <Layout>
      <section className="hero hero-compact">
        <p className="hero-kicker">Calculator</p>
        <h1 className="hero-title">
          Price your craft with <span className="accent">Eco Gnome</span>
        </h1>
        <p className="hero-tagline">
          Eco Gnome works out optimal buy and sell prices from your professions and their
          recipes, so a settler can price a table, a plank, or a whole supply chain without
          spreadsheets.
        </p>
      </section>

      <section className="cta-row">
        <a
          className="button button-primary"
          href={ECO_GNOME_URL}
          target="_blank"
          rel="noreferrer"
          data-testid="calc-open"
        >
          Open the calculator
        </a>
        <a className="button" href={ECO_GNOME_REPO} target="_blank" rel="noreferrer">
          Eco Gnome on GitHub
        </a>
      </section>

      <p className="intro">
        Today this opens the Eco-Gnome team's public instance, priced against vanilla Eco data.
        The plan for eco-app is to <strong>self-host</strong> it on this domain and feed it Sirens'
        actual modded recipes, skills, and items via the{" "}
        <a href={ECO_GNOME_MOD} target="_blank" rel="noreferrer">
          DataExporter mod
        </a>
        , so the numbers match <em>this</em> server rather than the vanilla defaults.
      </p>

      <p className="intro" data-testid="calc-attribution">
        Eco Gnome is <strong>MIT-licensed</strong>, built by the Eco-Gnome project (Zangdar and
        Joridan). eco-app self-hosts their work with attribution and license preserved - it does
        not fork the calculation engine or claim their tool as its own.
      </p>
    </Layout>
  )
}
