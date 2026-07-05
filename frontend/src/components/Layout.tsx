import type { ReactNode } from "react"
import { Link } from "react-router-dom"
import Footer from "./Footer"

interface LayoutProps {
  children: ReactNode
  fetchedAtISO?: string
}

// One flat surface: every page shares this topbar, so /, /server, and the
// server-rendered /jobs (which mirrors the same bar in Jinja) read as one
// site rather than separate spheres.
export default function Layout({ children, fetchedAtISO }: LayoutProps) {
  return (
    <div className="page">
      <header className="topbar">
        <Link to="/" className="wordmark">
          eco-app
        </Link>
        <nav className="topnav" aria-label="primary">
          <Link to="/">Home</Link>
          <Link to="/server">Server</Link>
          <Link to="/jobs">Jobs</Link>
          <Link to="/progression">Progression</Link>
          <Link to="/economy">Economy</Link>
          <Link to="/trade">Trade</Link>
          <Link to="/trades">Trades</Link>
          <Link to="/crafting">Crafting</Link>
          <Link to="/climate">Climate</Link>
          <Link to="/ecoregion">Ecoregion</Link>
          <Link to="/calculator">Calculator</Link>
          <Link to="/replay">Replay</Link>
        </nav>
      </header>

      <main className="content">{children}</main>

      <Footer fetchedAtISO={fetchedAtISO} />
    </div>
  )
}
