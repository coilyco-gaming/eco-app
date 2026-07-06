// Shared loading indicator. Heavy pages (the merged /map, eco-app#82) fetch
// several data planes at once and want one consistent "still working" line
// instead of a bare blank while they resolve. Reuses the existing `.loading`
// style + `data-testid="loading"` convention the /server and /jobs pages
// already lean on, so a test can wait on any page's loading state the same way.
export default function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <p className="loading" data-testid="loading" role="status" aria-live="polite">
      <span className="pulse-dot" aria-hidden="true" /> {label}
    </p>
  )
}
