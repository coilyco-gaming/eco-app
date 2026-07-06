import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import PagePassword from "./components/PagePassword"
import Calculator from "./pages/Calculator"
import Civics from "./pages/Civics"
import Climate from "./pages/Climate"
import Crafting from "./pages/Crafting"
import Economy from "./pages/Economy"
import Home from "./pages/Home"
import Item from "./pages/Item"
import Items from "./pages/Items"
import Jobs from "./pages/Jobs"
import MapPage from "./pages/Map"
import Progression from "./pages/Progression"
import Replay from "./pages/Replay"
import Server from "./pages/Server"
import Social from "./pages/Social"
import Trade from "./pages/Trade"
import Trades from "./pages/Trades"

// Route table for the SPA. The homepage is a thin directory of surfaces;
// per-feature pages (economy, map, species, milestones) join /server and
// /jobs here as they grow out of the design pass. The /jobs/* wildcard
// swallows the old server-rendered sub-paths (/jobs/professions etc.).
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
        <Route path="/progression" element={<Progression />} />
        <Route path="/economy" element={<Economy />} />
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
        <Route path="/calculator" element={<Calculator />} />
        <Route
          path="/replay"
          element={
            <PagePassword>
              <Replay />
            </PagePassword>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}
