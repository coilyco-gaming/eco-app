import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import PagePassword from "./components/PagePassword"
import Civics from "./pages/Civics"
import Climate from "./pages/Climate"
import Crafting from "./pages/Crafting"
import Home from "./pages/Home"
import Item from "./pages/Item"
import Items from "./pages/Items"
import Jobs from "./pages/Jobs"
import MapPage from "./pages/Map"
import Replay from "./pages/Replay"
import Server from "./pages/Server"
import Social from "./pages/Social"
import Trade from "./pages/Trade"
import Trades from "./pages/Trades"
import User from "./pages/User"
import Users from "./pages/Users"

// Route table for the SPA. The homepage is a thin directory of surfaces;
// per-feature pages (map, species, milestones) join /server and /jobs here as
// they grow out of the design pass. The /jobs/* wildcard swallows the old
// server-rendered sub-paths (/jobs/professions etc.).
//
// IA cleanup (eco-app#90): /calculator (the eco-gnome router) is now a homepage
// card, not a route; /economy is gone entirely; the standalone /progression
// page is folded into /jobs as its trajectory layer. Old links to those three
// redirect to their new home so nothing 404s.
//
// /social and /replay are URL-only: dropped from the nav and the homepage
// directory, and wrapped in PagePassword so they sit behind a soft password
// gate (eco-app#73). Everything else is open.
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/server" element={<Server />} />
        <Route path="/jobs/*" element={<Jobs />} />
        {/* /progression merged into /jobs (eco-app#90); keep old links alive. */}
        <Route path="/progression" element={<Navigate to="/jobs" replace />} />
        {/* /economy removed (eco-app#90); /calculator is a homepage card now. */}
        <Route path="/economy" element={<Navigate to="/" replace />} />
        <Route path="/calculator" element={<Navigate to="/" replace />} />
        <Route path="/trade" element={<Trade />} />
        <Route path="/trades" element={<Trades />} />
        <Route path="/crafting" element={<Crafting />} />
        <Route path="/items" element={<Items />} />
        <Route path="/item" element={<Item />} />
        <Route path="/civics" element={<Civics />} />
        <Route
          path="/social"
          element={
            <PagePassword>
              <Social />
            </PagePassword>
          }
        />
        <Route path="/map" element={<MapPage />} />
        <Route path="/climate" element={<Climate />} />
        {/* /world + /ecoregion merged into /map (eco-app#82); keep old links alive. */}
        <Route path="/world" element={<Navigate to="/map" replace />} />
        <Route path="/ecoregion" element={<Navigate to="/map" replace />} />
        <Route
          path="/replay"
          element={
            <PagePassword>
              <Replay />
            </PagePassword>
          }
        />
        {/* Hidden per-user surfaces (eco-app#80): no nav link, and — unlike
            /social and /replay — deliberately NOT behind PagePassword. /users
            lists every user; /users/<hex> is one user's dossier, keyed by the
            base16 of their username. */}
        <Route path="/users" element={<Users />} />
        <Route path="/users/:hex" element={<User />} />
      </Routes>
    </BrowserRouter>
  )
}
