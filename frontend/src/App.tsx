import { BrowserRouter, Route, Routes } from "react-router-dom"
import Home from "./pages/Home"
import Server from "./pages/Server"

// Route table for the SPA. The homepage is a thin directory of surfaces;
// per-feature pages (economy, map, species, milestones) join /server here
// as they grow out of the design pass.
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/server" element={<Server />} />
      </Routes>
    </BrowserRouter>
  )
}
