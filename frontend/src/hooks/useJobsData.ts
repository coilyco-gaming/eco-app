import { fetchJobsData, type JobsData } from "../lib/jobsApi"
import { useFreshData } from "../lib/useFreshData"

export interface JobsState {
  data: JobsData | null
  error: string | null
  loading: boolean
  /** Epoch ms of the last successful load, for the freshness caption. */
  loadedAt: number | null
  refreshing: boolean
  refreshError: string | null
  refresh: () => void
}

// Skills change on the minutes-to-hours scale, so the `jobs` contract is
// `manual`: no poll, but a Refresh control and a visible age (eco-app#201).
// This used to be a hand-rolled mount-only effect with a comment claiming "a
// refresh is a re-fetch" — true only if the reader reloaded the whole page,
// because nothing on screen offered one.
export function useJobsData(): JobsState {
  const { data, error, loading, loadedAt, refreshing, refreshError, refresh } =
    useFreshData("jobs", fetchJobsData)
  return { data, error, loading, loadedAt, refreshing, refreshError, refresh }
}
