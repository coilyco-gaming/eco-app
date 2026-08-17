# Trade watchers

Standing queries over the trades feed, evaluated without resetting.

## The no-reset spine

A watcher has two readings, and conflating them is the bug this design avoids.
The **feed** is matching trades with a `time` past the watcher's stored
last-seen, which advances. The **display** is the current matching state: how
many trades match right now, which does not.

Reading the display never advances the feed, so opening a page cannot cause a
notification to be missed.

## Query kinds

- **`item`** - match a trade's item, by raw Eco name (`IronIngotItem`) or its
  prettified form.
- **`store`** - match the `WorldObjectItem` the trade happened at.
- **`trader`** - match any party, buyer, seller, or shop owner, by resolved
  name.
- **`price`** - an item plus a threshold predicate on unit price, such as iron
  ingots under a given figure.

## Surfaces

- **`trade_watchers`** - `src/eco_mcp_app/watchers.py`. The MCP tool
  multiplexes create, list, remove, and the state-advancing evaluate, which is
  why it is not yet dual-registered.
- **`/trade` sidebar** - `frontend/src/pages/Trade.tsx`, consuming the
  read-only peek at `/preview/watchers.json`.

**Persistence.** Watchers persist across restarts, and evaluation is idempotent
for a given last-seen, so a repeated evaluate at the same position returns the
same feed rather than draining it. Tests cover each query kind, the no-reset
property, and the multiplexed tool's four actions.

See also: [trades.md](trades.md), [dual-route-inventory.md](dual-route-inventory.md).
