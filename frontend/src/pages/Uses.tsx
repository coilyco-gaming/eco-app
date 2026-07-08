import { Link } from "react-router-dom"
import Layout from "../components/Layout"

// The /uses hub: a single directory of task-framed use-case pages. This is the
// ONLY homepage card the whole use-case family gets (eco-app#99) — the
// individual pages are URL-only, reached from here, mirroring how /item is only
// reached from /items.
//
// The four demand-side pages below read data eco-app already hydrates (the same
// planes /trade renders), so they ship in this no-dependency slice. The
// recipe-dependent use cases (follow-ups A–E on eco-app#98, gated on the recipe
// exporter) show as muted "coming soon" cards so the hub reads as the full
// roadmap without pretending they are built.

interface UseCard {
  to: string
  testid: string
  title: string
  blurb: string
}

const LIVE: UseCard[] = [
  {
    to: "/uses/demand",
    testid: "use-demand",
    title: "What's in demand right now",
    blurb: "The items buyers want that nobody is stocking — ranked, with who needs each.",
  },
  {
    to: "/uses/buy-sell",
    testid: "use-buy-sell",
    title: "Where to buy X cheapest / sell X highest",
    blurb: "Pick an item, see the cheapest shelves to buy from and the best shelves to sell into.",
  },
  {
    to: "/uses/arbitrage",
    testid: "use-arbitrage",
    title: "Buy low here, sell high there",
    blurb: "Cross-store spreads: buy at one shop, sell at another, ranked by the opportunity.",
  },
  {
    to: "/uses/price",
    testid: "use-price",
    title: "How should I price X?",
    blurb: "Compare the market band, shelf comparison, and craft cost before you post an ask.",
  },
  {
    to: "/uses/shop-check",
    testid: "use-shop-check",
    title: "Is my shop priced right?",
    blurb: "Pick your store, compare every item's price against the market median.",
  },
]

// The recipe-dependent Tier B/C use cases from eco-app#98 — gated on the recipe
// exporter, deliberately not built here. Listed muted so the hub is the whole
// roadmap, not just the slice that shipped.
const SOON: Array<{ title: string; blurb: string }> = [
  {
    title: "What's X made from / used in",
    blurb: "The recipe tree around an item — ingredients up, products down.",
  },
  {
    title: "Value per profession",
    blurb: "Which skills earn the most per craft, from recipe cost and market price.",
  },
]

export default function Uses() {
  return (
    <Layout>
      <section className="hero hero-compact">
        <h1 className="hero-title">
          What is eco-app <span className="accent">useful for</span>?
        </h1>
        <p className="hero-tagline">
          Task-framed pages that turn the live economy into a decision — pick the job you're doing.
        </p>
      </section>

      <section className="dir-cards" aria-label="use cases">
        {LIVE.map((c) => (
          <Link className="dir-card" to={c.to} key={c.to} data-testid={c.testid}>
            <h3>{c.title} →</h3>
            <p>{c.blurb}</p>
          </Link>
        ))}
      </section>

      <section>
        <h2 className="section-title">
          Coming soon <span className="section-sub">(needs the recipe exporter — eco-app#98)</span>
        </h2>
        <div className="dir-cards" aria-label="coming soon">
          {SOON.map((c) => (
            <div className="dir-card dir-card-static" key={c.title} data-testid="use-soon">
              <h3>{c.title}</h3>
              <p>{c.blurb}</p>
            </div>
          ))}
        </div>
      </section>
    </Layout>
  )
}
