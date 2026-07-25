# Use-case hub + demand-side pages

The practical-usefulness layer: a `/uses` hub plus task-framed links that turn
the live economy and recipe graph into a decision. The five dedicated use-case
pages came from follow-up **F** in the design from
[#98](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/98), filed as
[#99](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/99). The hub
also routes recipe and profession-value decisions to the completed `/recipes`
and `/jobs` surfaces.

## The hub

`/uses` (`frontend/src/pages/Uses.tsx`) is a single directory page. It is the
**only** homepage card the whole use-case family gets (`dir-uses` on
`Home.tsx`) - the five pages below are **URL-only**, reached from the hub,
mirroring how `/item` is only reached from `/items`.

The five demand-side pages show as live, linked cards. The hub also links the
recipe graph at `/recipes` for "what is X made from / used in" and the
profession-value board on `/jobs`. Those recipe-dependent capabilities shipped
through [#100](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/100)
to [#103](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/103), so
the hub no longer presents them as future work. The priced use case ships as
the live `/uses/price` page.

## The demand-side pages

- **`/uses/demand` - "What's in demand right now"** (`UsesDemand.tsx`) - ranks the logistics **supply gaps** (`LogisticsBoard.supplyGaps`) by `demandQty`. Each row names the item, a `reason` severity tag (`no_supply` / `thin_supply` / `overpriced`) rendered glyph+label+colour (never colour alone), the quantity wanted and buyer count, and a **who-needs-it** line naming each buyer, how much they still want, and at what price.
- **`/uses/buy-sell` - "Where to buy X cheapest / sell X highest"** (`UsesBuySell.tsx`) - picks an item via `?item=<id>` (deep-linkable) from a filter list of everything on the shelves. For the picked item it shows the **cheapest sell** offers (from the logistics `cheapest` board, sorted low-to-high) and the **best buy** offers (from the `resale` board, sorted high-to-low), each row naming the store, owner, price, quantity, and live/history source.
- **`/uses/arbitrage` - "Buy low here, sell high there"** (`UsesArbitrage.tsx`) - renders the cross-store **arbitrage spreads** (`LogisticsBoard.arbitrage`) ranked by `opportunity`: buy-from store, sell-to store, spread and spread percent, movable volume, and the opportunity score.
- **`/uses/price` - "How should I price X?"** (`UsesPrice.tsx`) - picks an item via `?item=<id>` and leads with the **fair-price band** from the market's daily buckets (median plus an IQR band over bucket medians), the **current shelf comparison** from logistics (`cheapest` / `resale`) with market trend direction, the **recipe cost roll-up** when the cost plane is present, and the **suggested ask** at a target markup over craft cost. For the five FRED-pegged commodities it overlays the real-world benchmark and verdict from `fair_price.py`; every panel still degrades independently via `fetchJsonOrNull`.
- **`/uses/shop-check` - "Is my shop priced right?"** (`UsesShopCheck.tsx`) - picks a store via `?store=<key>` and, for each item it lists, compares the store's own `avgUnitPrice` (from `/preview/stores.json`) against the **market median** (from `/preview/market.json`), flagging items priced past ±15% over or under market with a glyph+label+colour verdict. This is the one page that **joins two planes**, so it degrades to a clear note when either is unavailable.

## Conventions followed

- **Degrade independently.** Every panel reads its plane through `fetchJsonOrNull` (via the typed `lib/*Api.ts` clients), so a sibling that 404s on a reset-gated shelf resolves to null and its panel degrades in place rather than blanking the page. Nothing new is fetched - these pages reuse the `/trade` logistics, stores, and market clients wholesale.
- **One heading tier + one intro line per page**, matching the [#97](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/97) cleanup direction - no stacked intros. Sub-pages carry a back-to-hub link and a single job-stating hero title.
- **Deep-linkable** via `?item=` / `?store=` so QA can share a link to an exact view. `formatCount` / `prettifyEcoName` from `lib/format.ts` do the number and item-name rendering.
- **Tests** - one vitest component test per page (`*.test.tsx`), each covering the happy path (ranking / joining / deep-link) and the degraded-when-null branch, mirroring `pages/Trade.test.tsx` and `pages/Items.test.tsx`.

## Product boundary

The five dedicated `/uses/*` pages stay demand-side focused. The hub reuses the
existing `/recipes` and `/jobs` surfaces for recipe exploration and
profession-value decisions instead of duplicating those capabilities under new
routes.

## See also

- [docs/FEATURES.md](FEATURES.md) - inventory entry for this hub.
- [docs/trades.md](trades.md) - the trades ledger these boards fold from.
- The `/trade` surface (`frontend/src/pages/Trade.tsx`) - the full market page the demand-side pages carve focused views out of.
