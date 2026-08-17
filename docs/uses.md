# The uses hub

Task-shaped entry points into the trade data, one page per question a player
actually asks.

## The demand-side pages

- **`/uses/demand`**, "what's in demand right now" (`UsesDemand.tsx`) - ranks
  the logistics supply gaps from `LogisticsBoard`.
- **`/uses/buy-sell`**, "where to buy X cheapest, sell X highest"
  (`UsesBuySell.tsx`) - picks an item through `?item=<id>`.
- **`/uses/arbitrage`**, "buy low here, sell high there"
  (`UsesArbitrage.tsx`) - renders cross-store spreads.
- **`/uses/price`**, "how should I price X?" (`UsesPrice.tsx`) - picks an item
  and currency through `?item=<id>&currency=<name>`.
- **`/uses/shop-check`**, "is my shop priced right?" (`UsesShopCheck.tsx`) -
  picks a store through `?store=<key>` and compares each item it carries.

## Conventions

- **Degrade independently.** Every panel reads its plane through
  `fetchJsonOrNull` and the typed `lib/*Api.ts` clients, so one dead plane
  leaves its siblings rendering.
- **One heading tier and one intro line per page**, matching #97.
- **Deep-linkable** through `?item=` and `?store=`, so a link names an exact
  view. `formatCount` and `prettifyEcoName` come from `lib/`.
- **Tests** - one vitest component test per page, each covering the happy path
  and the degraded path.

## Product boundary

These pages answer questions. They do not hold state, do not write, and do not
introduce a data plane of their own: every number on them comes from a plane
another surface already owns, which is what keeps the hub cheap to extend.

See also: [trades.md](trades.md), [price-history.md](price-history.md),
[cost.md](cost.md).
