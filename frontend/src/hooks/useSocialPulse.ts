import { useEffect, useState } from "react"
import { fetchSocial } from "../lib/socialApi"

export interface SocialPulse {
  chat: number
  arrivals: number
}

// Live badge feed for the homepage /social card: a one-shot fetch of the social
// surface, folded to chat volume + new-arrival counts. Best-effort — a missing
// or failing endpoint leaves the badge absent rather than surfacing an error,
// the same graceful-degrade contract the /social page itself keeps (eco-app#63).
export function useSocialPulse(): SocialPulse | null {
  const [pulse, setPulse] = useState<SocialPulse | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchSocial(controller.signal)
      .then((surface) => {
        if (controller.signal.aborted) return
        setPulse({ chat: surface.totalChat, arrivals: surface.totalFirstLogins })
      })
      .catch(() => {
        /* non-fatal: leave the badge absent */
      })
    return () => controller.abort()
  }, [])

  return pulse
}
