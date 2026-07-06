// Shared loading-state indicator for the heavier pages (the map and social
// surfaces, and the /replay and /social gate below them, all use this). A
// spinning leaf ring plus a label, wired for assistive tech via role=status.
// One component so every "…still fetching" moment reads the same across the
// SPA instead of each page hand-rolling its own `.loading` paragraph.
interface LoadingProps {
  label?: string
  testid?: string
}

export default function Loading({ label = "Loading…", testid = "loading" }: LoadingProps) {
  return (
    <p className="loading" role="status" aria-live="polite" data-testid={testid}>
      <span className="loading-spinner" aria-hidden="true" />
      {label}
    </p>
  )
}
