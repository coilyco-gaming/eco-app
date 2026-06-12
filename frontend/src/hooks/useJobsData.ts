import { useEffect, useState } from "react"
import { fetchJobsData, type JobsData } from "../lib/jobsApi"

export interface JobsState {
  data: JobsData | null
  error: string | null
  loading: boolean
}

// One fetch per visit: skills change on the minutes-to-hours scale, so no
// poll. A refresh is a re-fetch.
export function useJobsData(): JobsState {
  const [state, setState] = useState<JobsState>({ data: null, error: null, loading: true })

  useEffect(() => {
    const controller = new AbortController()

    fetchJobsData(controller.signal)
      .then((data) => setState({ data, error: null, loading: false }))
      .catch((err) => {
        if (controller.signal.aborted) return
        setState({
          data: null,
          error: err instanceof Error ? err.message : String(err),
          loading: false,
        })
      })

    return () => controller.abort()
  }, [])

  return state
}
