import { BrowserRouter, Route, Routes } from "react-router-dom"
import Home from "./pages/Home"
import Jobs from "./pages/Jobs"
import Server from "./pages/Server"

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
      </Routes>
    </BrowserRouter>
  )
}
