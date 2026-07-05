import { BrowserRouter, Route, Routes } from "react-router-dom"
import Calculator from "./pages/Calculator"
import Climate from "./pages/Climate"
import Crafting from "./pages/Crafting"
import Ecoregion from "./pages/Ecoregion"
import Economy from "./pages/Economy"
import Home from "./pages/Home"
import Jobs from "./pages/Jobs"
import Server from "./pages/Server"
import Trade from "./pages/Trade"
import Trades from "./pages/Trades"

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
        <Route path="/economy" element={<Economy />} />
        <Route path="/trade" element={<Trade />} />
        <Route path="/trades" element={<Trades />} />
        <Route path="/crafting" element={<Crafting />} />
        <Route path="/climate" element={<Climate />} />
        <Route path="/ecoregion" element={<Ecoregion />} />
        <Route path="/calculator" element={<Calculator />} />
      </Routes>
    </BrowserRouter>
  )
}
