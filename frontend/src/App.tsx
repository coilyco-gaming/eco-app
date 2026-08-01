import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import PagePassword from "./components/PagePassword"
import Civics from "./pages/Civics"
import Crafting from "./pages/Crafting"
import Home from "./pages/Home"
import Info from "./pages/Info"
import Item from "./pages/Item"
import Items from "./pages/Items"
import Jobs from "./pages/Jobs"
import MapPage from "./pages/Map"
import Mods from "./pages/Mods"
import Recipe from "./pages/Recipe"
import Recipes from "./pages/Recipes"
import Replay from "./pages/Replay"
import Social from "./pages/Social"
import Trade from "./pages/Trade"
import User from "./pages/User"
import Uses from "./pages/Uses"
import UsesArbitrage from "./pages/UsesArbitrage"
import UsesBuySell from "./pages/UsesBuySell"
import UsesDemand from "./pages/UsesDemand"
import UsesFood from "./pages/UsesFood"
import UsesPrice from "./pages/UsesPrice"
import UsesShopCheck from "./pages/UsesShopCheck"
import Wiki from "./pages/Wiki"

// Route table for the SPA. The homepage is a thin directory of surfaces;
// per-feature pages (map, species, milestones) join /info and /jobs here as
// they grow out of the design pass. The /jobs/* wildcard swallows the old
// server-rendered sub-paths (/jobs/professions etc.).
//
// IA cleanup (eco-app#90): /calculator (the eco-gnome router) is now a homepage
// card, not a route; /economy is gone entirely; the standalone /progression
// page is folded into /jobs as its trajectory layer; /server is renamed /info;
// the /trades ledger is folded into /trade; and /climate is folded into the
// World map (/map) as an environmental overlay. Old links to every retired path
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
        <Route path="/info" element={<Info />} />
        <Route path="/mods" element={<Mods />} />
        <Route path="/wiki" element={<Wiki />} />
        {/* /server renamed to /info (eco-app#90); keep old links alive. */}
        <Route path="/server" element={<Navigate to="/info" replace />} />
        <Route path="/jobs/*" element={<Jobs />} />
        {/* /progression merged into /jobs (eco-app#90); keep old links alive. */}
        <Route path="/progression" element={<Navigate to="/jobs" replace />} />
        {/* /economy removed (eco-app#90); /calculator is a homepage card now. */}
        <Route path="/economy" element={<Navigate to="/" replace />} />
        <Route path="/calculator" element={<Navigate to="/" replace />} />
        <Route path="/trade" element={<Trade />} />
        {/* /trades ledger folded into /trade (eco-app#90); keep old links alive. */}
        <Route path="/trades" element={<Navigate to="/trade" replace />} />
        <Route path="/crafting" element={<Crafting />} />
        <Route path="/items" element={<Items />} />
        <Route path="/item" element={<Item />} />
        {/* Recipe browse (eco-app#101): /recipes is the directory, /recipe?id=
            the per-recipe detail, URL-only and reached only from /recipes —
            mirroring /items -> /item. */}
        <Route path="/recipes" element={<Recipes />} />
        <Route path="/recipe" element={<Recipe />} />
        <Route path="/civics" element={<Civics />} />
        {/* The /uses hub + its demand-side use-case pages (eco-app#99). The
            hub gets the only homepage card; the four pages below are URL-only,
            reached from the hub, mirroring how /item is reached only from
            /items. */}
        <Route path="/uses" element={<Uses />} />
        <Route path="/uses/demand" element={<UsesDemand />} />
        <Route path="/uses/food" element={<UsesFood />} />
        <Route path="/uses/buy-sell" element={<UsesBuySell />} />
        <Route path="/uses/arbitrage" element={<UsesArbitrage />} />
        <Route path="/uses/price" element={<UsesPrice />} />
        <Route path="/uses/shop-check" element={<UsesShopCheck />} />
        <Route
          path="/social"
          element={
            <PagePassword>
              <Social />
            </PagePassword>
          }
        />
        <Route path="/map" element={<MapPage />} />
        {/* /world + /ecoregion merged into /map (eco-app#82) and /climate folded
            in as the World page's environmental overlay (eco-app#90); keep the
            old links alive. The page is titled "World" — the canonical path
            stays /map to avoid clashing with the get_eco_world data plane. */}
        <Route path="/world" element={<Navigate to="/map" replace />} />
        <Route path="/ecoregion" element={<Navigate to="/map" replace />} />
        <Route path="/climate" element={<Navigate to="/map" replace />} />
        <Route
          path="/replay"
          element={
            <PagePassword>
              <Replay />
            </PagePassword>
          }
        />
        {/* Hidden per-user dossier (eco-app#80): no nav link, and — unlike
            /social and /replay — deliberately NOT behind PagePassword.
            /users/<hex> is one user's dossier, keyed by the base16 of their
            username. The all-users /users listing was removed in eco-app#93;
            the old path now redirects to the homepage rather than 404ing. */}
        <Route path="/users" element={<Navigate to="/" replace />} />
        <Route path="/users/:hex" element={<User />} />
      </Routes>
    </BrowserRouter>
  )
}
