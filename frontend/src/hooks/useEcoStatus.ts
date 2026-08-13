import { fetchEcoStatus, type EcoStatus } from "../lib/api"
import { useFreshData } from "../lib/useFreshData"

export interface EcoStatusState {
  status: EcoStatus | null
  error: string | null
  loading: boolean
  /** Epoch ms of the last successful load, for the freshness caption. */
  loadedAt: number | null
  refreshing: boolean
  refreshError: string | null
  refresh: () => void
}

// Fetch the live server snapshot and keep it fresh. The page stays useful when
// the game server is unreachable: callers get `error` and render a degraded
// snapshot instead of breaking the hero/CTA shell.
//
// This was the only plane on the site that already polled. It now goes through
// the shared contract (eco-app#201) so it keeps its 60s cadence *and* gains the
// things it was missing: a load timestamp, a manual refresh, and a refresh
// failure that does not blank data already on screen.
export function useEcoStatus(server = ""): EcoStatusState {
  const { data, error, loading, loadedAt, refreshing, refreshError, refresh } =
    useFreshData("status", (signal) => fetchEcoStatus(server, signal), [server])
  return { status: data, error, loading, loadedAt, refreshing, refreshError, refresh }
}
