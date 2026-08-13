# SPA refresh contracts

Every data plane the SPA fetches declares, in one place, how often its source
can advance and what an open page does about it. Built for
[eco-app#201](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/201),
which generalised
[eco-app#184](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/184) —
the public world page showing pollution numbers that had not moved in over 12
hours.

## The three modes

| Mode | Behaviour | What the page says |
|---|---|---|
| `live` | Polls on its contract cadence | "updated 40s ago" |
| `manual` | No timer; a Refresh control | "loaded 3m ago · Refresh" |
| `static` | Cannot advance within a session | "loaded 5m ago · this data does not change while the page is open" |

A `live` plane that ages past its stale window stops looking current and says
"not refreshing, reload the page". That is the eco-app#184 failure, made
visible instead of silent.

## Three different ages, never conflated

- **Browser load age** — when this tab last received data. This is what the
  caption counts, and it is the only one the frontend knows for certain.
- **Backend fetch age** — when the service last called the game server. Shown
  separately as "server observed …" when the payload carries `fetchedAtISO`.
- **Source observation age** — when the game server itself sampled the value.
  Mostly unknown, and never inferred from either of the above.

Backend fetch time is not source observation time. Presenting one as the other
is the specific error eco-app#184 warns against.

## Where the values live

`frontend/src/lib/freshness.ts` holds the contract table. Cadences live there,
not in components, so they are tunable in one place and so tests assert
behaviour rather than restating constants.

`frontend/src/lib/useFreshData.ts` is the single fetch path. It handles the
mount load, the poll (driven by the contract, not by the component), the manual
refresh, and the distinction between a failed first load and a failed refresh —
a failed refresh keeps the last good data on screen rather than blanking the
page.

`frontend/src/components/FreshnessNote.tsx` renders the contract. Its caption
re-renders on its own timer, so an idle page keeps ageing truthfully even on a
plane that never refetches.

## Adding a plane

1. Add an entry to `REFRESH_CONTRACTS` with a mode and a rationale. The test
   suite fails if a plane has no rationale, if a `live` plane has no poll period
   or a stale window shorter than its poll period, or if a `static` plane polls.
2. Fetch it with `useFreshData("<plane>", fetcher)`.
3. Render a `<FreshnessNote plane="<plane>" … />` near the top of the section
   it describes.

## Wiring status

**Every SPA data plane is wired.** No page or hook fetches on mount without a
declared contract; `useFreshData` is the only fetch path.

That includes the eight homepage "pulse" badge hooks, which were the easiest
planes to miss — they live in `hooks/`, not `pages/`, so a sweep of the page
directory does not see them. Two of them read `live` planes, so a homepage left
open now keeps its badges current instead of freezing them at whatever the tab
first read.

Two shapes worth knowing about:

- **Composite planes** (`trade`, `shopCheck`, `resolve`) belong to a page that
  fans out to several sources. Their members refresh together, because a
  summary stitched from reads minutes apart is worse than one that is uniformly
  a few minutes old. Every member stays best-effort: one source resolving to
  null thins the board rather than failing the page.
- **Parameterised pages** pass their URL key in the hook's `deps`, so a changed
  item, species or user re-fetches. `/species` and `/item` additionally gate on
  the identifier their payload names, so a slow response for a previous query
  can never render against the current one.

The two remaining raw effects in `/uses/price` are deliberate: they key on
`item` and `selectedCurrency` and already re-run when those change, so they were
never page-load-only. Only the page-level market spine there needed a contract.
