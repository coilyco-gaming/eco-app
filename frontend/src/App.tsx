import { BrowserRouter, Route, Routes } from "react-router-dom"
import Landing from "./pages/Landing"

// Route table for the SPA. Per-feature dashboard pages (economy, map,
// species, milestones) land here as they grow out of the design pass.
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
      </Routes>
    </BrowserRouter>
  )
}
