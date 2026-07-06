import type { ReactNode } from "react"
import { Link } from "react-router-dom"
import Footer from "./Footer"

interface LayoutProps {
  children: ReactNode
  fetchedAtISO?: string
}

// One flat surface: every page shares this topbar, so /, /info, and /jobs read
// as one site rather than separate spheres. The nav mirrors the collapsed page
// set from the eco-app#90 IA cleanup — progression lives inside Jobs, the
// trades ledger inside Trade, and climate inside World, so they get no nav
// entry of their own; Server is renamed Info and Map is titled World.
export default function Layout({ children, fetchedAtISO }: LayoutProps) {
  return (
    <div className="page">
      <header className="topbar">
        <Link to="/" className="wordmark">
          eco-app
        </Link>
        <nav className="topnav" aria-label="primary">
          <Link to="/">Home</Link>
          <Link to="/info">Info</Link>
          <Link to="/jobs">Jobs</Link>
          <Link to="/trade">Trade</Link>
          <Link to="/items">Items</Link>
          <Link to="/crafting">Crafting</Link>
          <Link to="/map">World</Link>
        </nav>
      </header>

      <main className="content">{children}</main>

      <Footer fetchedAtISO={fetchedAtISO} />
    </div>
  )
}
