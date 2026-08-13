// The one fetch path every SPA page uses, so no plane can quietly go
// mount-only again (eco-app#201).
//
// Replaces the hand-rolled `useEffect(() => { fetchX().then(setX) }, [])` that
// nearly every page had. That shape fetched once and never again, so an open
// tab drifted from its source with nothing on screen to say so — the general
// case behind eco-app#184's frozen pollution numbers.
//
// What a caller gets: the data, the error, whether a refresh is in flight,
// when this tab last received data, and a `refresh()` it can wire to a button.
// Polling is driven by the plane's contract in `freshness.ts`, never by a
// number typed into a component.

import { useCallback, useEffect, useReducer, useRef } from "react"

import { contractFor, type PlaneName } from "./freshness"

export interface FreshData<T> {
  data: T | null
  error: string | null
  /** True only for the initial load, so a refresh never blanks the page. */
  loading: boolean
  /** True while a background poll or a manual refresh is in flight. */
  refreshing: boolean
  /** Epoch ms when this tab last received data. Null until the first success. */
  loadedAt: number | null
  /** Set when a refresh failed but earlier data is still on screen. */
  refreshError: string | null
  refresh: () => void
}

interface State<T> {
  data: T | null
  error: string | null
  loading: boolean
  refreshing: boolean
  loadedAt: number | null
  refreshError: string | null
}

type Action<T> =
  | { type: "start"; initial: boolean }
  | { type: "success"; data: T; at: number }
  | { type: "failure"; message: string }

function reducer<T>(state: State<T>, action: Action<T>): State<T> {
  switch (action.type) {
    case "start":
      return action.initial
        ? { ...state, loading: true, refreshing: false }
        : { ...state, refreshing: true }
    case "success":
      return {
        data: action.data,
        error: null,
        loading: false,
        refreshing: false,
        loadedAt: action.at,
        // A recovered refresh clears the previous failure, or the page keeps
        // apologising for something that is no longer true.
        refreshError: null,
      }
    case "failure":
      // Keep showing stale-but-real data when a refresh fails; only a failed
      // *first* load is a page-level error.
      return state.data === null
        ? { ...state, loading: false, refreshing: false, error: action.message }
        : { ...state, loading: false, refreshing: false, refreshError: action.message }
  }
}

const INITIAL = {
  data: null,
  error: null,
  loading: true,
  refreshing: false,
  loadedAt: null,
  refreshError: null,
}

export function useFreshData<T>(
  plane: PlaneName,
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[] = [],
): FreshData<T> {
  const [state, dispatch] = useReducer(reducer<T>, INITIAL as State<T>)
  // Held in a ref so the polling effect never re-subscribes when the caller
  // passes a new closure on every render. Only read inside callbacks/effects.
  const fetcherRef = useRef(fetcher)
  useEffect(() => {
    fetcherRef.current = fetcher
  })

  const depsKey = JSON.stringify(deps)

  const run = useCallback(
    async (signal: AbortSignal, initial: boolean) => {
      dispatch({ type: "start", initial })
      try {
        const next = await fetcherRef.current(signal)
        if (signal.aborted) return
        dispatch({ type: "success", data: next, at: Date.now() })
      } catch (err) {
        if (signal.aborted) return
        dispatch({ type: "failure", message: err instanceof Error ? err.message : String(err) })
      }
    },
    [dispatch],
  )

  // Manual refresh. Its own controller so it never cancels the mount fetch.
  const refresh = useCallback(() => {
    void run(new AbortController().signal, false)
  }, [run])

  useEffect(() => {
    const controller = new AbortController()
    void run(controller.signal, true)

    const { mode, pollMs } = contractFor(plane)
    if (mode !== "live" || !pollMs) {
      return () => controller.abort()
    }
    const timer = setInterval(() => {
      // A background tab should not keep polling a game server.
      if (typeof document !== "undefined" && document.hidden) return
      void run(new AbortController().signal, false)
    }, pollMs)
    return () => {
      controller.abort()
      clearInterval(timer)
    }
    // `depsKey` stands in for the caller's deps: a changed key is a different
    // question, so the plane reloads from scratch.
  }, [plane, run, depsKey])

  return { ...state, refresh }
}
