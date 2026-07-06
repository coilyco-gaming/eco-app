import { BrowserRouter, Route, Routes } from "react-router-dom"
import Calculator from "./pages/Calculator"
import Civics from "./pages/Civics"
import Climate from "./pages/Climate"
import Crafting from "./pages/Crafting"
import Ecoregion from "./pages/Ecoregion"
import Economy from "./pages/Economy"
import Home from "./pages/Home"
import Jobs from "./pages/Jobs"
import Progression from "./pages/Progression"
import Replay from "./pages/Replay"
import Server from "./pages/Server"
import Social from "./pages/Social"
import Trade from "./pages/Trade"
import Trades from "./pages/Trades"
import User from "./pages/User"
import Users from "./pages/Users"
import World from "./pages/World"

// Route table for the SPA. The homepage is a thin directory of surfaces;
// per-feature pages (economy, map, species, milestones) join /server and
// /jobs here as they grow out of the design pass. The /jobs/* wildcard
// swallows the old server-rendered sub-paths (/jobs/professions etc.).
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/server" element={<Server />} />
        <Route path="/jobs/*" element={<Jobs />} />
        <Route path="/progression" element={<Progression />} />
        <Route path="/economy" element={<Economy />} />
        <Route path="/trade" element={<Trade />} />
        <Route path="/trades" element={<Trades />} />
        <Route path="/crafting" element={<Crafting />} />
        <Route path="/civics" element={<Civics />} />
        <Route path="/social" element={<Social />} />
        <Route path="/world" element={<World />} />
        <Route path="/climate" element={<Climate />} />
        <Route path="/ecoregion" element={<Ecoregion />} />
        <Route path="/calculator" element={<Calculator />} />
        <Route path="/replay" element={<Replay />} />
        {/* Hidden per-user surfaces (eco-app#80): no nav link, not password-
            protected. /users lists every user; /users/<hex> is one user's
            dossier, keyed by the base16 of their username. */}
        <Route path="/users" element={<Users />} />
        <Route path="/users/:hex" element={<User />} />
      </Routes>
    </BrowserRouter>
  )
}
