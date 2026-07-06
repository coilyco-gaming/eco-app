import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import Layout from "../components/Layout"
import { formatCount } from "../lib/format"
import { encodeUserHex, fetchUsersIndex, type UsersIndex } from "../lib/usersApi"

// The hidden /users directory (eco-app#80). Lists *every* user seen across all
// exporters — the "list every user, never a truncated top-N" rule made literal
// — each linking to their /users/<hex> dossier. Hidden: no nav link.
export default function Users() {
  const [index, setIndex] = useState<UsersIndex | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchUsersIndex(controller.signal)
      .then(setIndex)
      .catch((err) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err))
      })
    return () => controller.abort()
  }, [])

  return (
    <Layout fetchedAtISO={index?.fetchedAtISO}>
      <section className="hero hero-compact">
        <p className="hero-kicker">Users</p>
        <h1 className="hero-title">
          Every <span className="accent">player</span>, one page each
        </h1>
        {index && (
          <p className="hero-pill" data-testid="users-pill">
            <span className="pulse-dot" aria-hidden="true" />
            {formatCount(index.users.length)} users across all exporters
          </p>
        )}
        {!index && error && (
          <p className="hero-pill hero-pill-muted" data-testid="users-error">
            user directory unavailable right now
          </p>
        )}
        <p className="redaction-note">
          Every user the server exports, never a truncated top-N. Each links to a full per-user
          dossier. Hidden by design — no nav link, no password.
        </p>
      </section>

      {index && index.users.length === 0 && (
        <section>
          <p className="empty-note" data-testid="users-empty">
            No users recorded on this server yet.
          </p>
        </section>
      )}

      {index && index.users.length > 0 && (
        <section>
          <ul className="rank-rows" data-testid="users-list">
            {index.users.map((name) => (
              <li key={name}>
                <Link className="rank-row" to={`/users/${encodeUserHex(name)}`} data-testid="user-link">
                  <span className="rank-name">{name}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </Layout>
  )
}
