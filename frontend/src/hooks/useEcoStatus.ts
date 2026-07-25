import { useEffect, useState } from "react"
import { fetchEcoStatus, type EcoStatus } from "../lib/api"

const POLL_INTERVAL_MS = 60_000

export interface EcoStatusState {
  status: EcoStatus | null
  error: string | null
  loading: boolean
}

// Fetch the live server snapshot and keep it fresh. The page stays useful
// when the game server is unreachable: callers get `error` and render a
// degraded snapshot instead of breaking the hero/CTA shell.
export function useEcoStatus(server = ""): EcoStatusState {
  const [state, setState] = useState<EcoStatusState>({
    status: null,
    error: null,
    loading: true,
  })

  useEffect(() => {
    const controller = new AbortController()
    setState({ status: null, error: null, loading: true })

    async function load() {
      try {
        const status = await fetchEcoStatus(server, controller.signal)
        if (controller.signal.aborted) return
        setState({ status, error: null, loading: false })
      } catch (err) {
        if (controller.signal.aborted) return
        setState((prev) => ({
          status: prev.status,
          error: err instanceof Error ? err.message : String(err),
          loading: false,
        }))
      }
    }

    void load()
    const timer = setInterval(() => void load(), POLL_INTERVAL_MS)
    return () => {
      controller.abort()
      clearInterval(timer)
    }
  }, [server])

  return state
}
