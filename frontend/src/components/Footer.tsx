import { formatFetchedAt } from "../lib/format"

export default function Footer({ fetchedAtISO }: { fetchedAtISO?: string }) {
  return (
    <footer className="site-footer">
      <p>
        Unofficial fan project. Eco is a trademark of{" "}
        <a href="https://strangeloopgames.com/">Strange Loop Games</a>.
      </p>
      {fetchedAtISO && <p className="footer-stamp">snapshot {formatFetchedAt(fetchedAtISO)}</p>}
    </footer>
  )
}
