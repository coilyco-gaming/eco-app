# Bottom-up cost roll-up engine

The piece that turns recipe definitions into a **cost to craft one unit**, so
margin ("`medianUnitPrice - rolledUpCost`") and "is this worth crafting" finally
become answerable. Follow-up **C** on the recipe/pricing roadmap
([#98](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/98),
[#102](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/102)),
built on the two halves that already existed:

- **`recipes.py`** (follow-up A, [#100](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/100)) - the
  bill-of-materials: ingredients-in / product-out, station, skill, `laborCost`
  (calories), `craftMinutes`, and the `byProduct` / `tags` lookup maps the
  recursion walks.
- **`market.py`** (from [#49](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/49)) - the
  per-item median trade price that prices each leaf ingredient.

`cost.py` fuses them. This ticket lands the **engine + data plane** only; the
value-per-profession page (D) and the "how to price X" page (E) are the
consumers that light up on top of it.

## The model

Bottom-up and recursive over the ingredient edges A exposes:

- **Ingredient cost (make-or-buy).** For each ingredient the engine takes the
  **cheaper** of buying it at market median or crafting it from its own recipe,
  and follows that decision recursively down to raw leaves. A **leaf** - a raw
  resource with no producing recipe - is priced at its market median. A leaf with
  **no** market price is surfaced as an **unpriced input**, never silently
  zeroed: its recipe reports `complete: false`, a `null` `perUnitCost`, and the
  offending item id in `unpricedInputs`.
- **Labor + calories.** Eco meters labor in **calories**. Every recipe the engine
  actually crafts folds its labor calories into that node's cost at a
  caller-supplied `caloriePrice` (currency per calorie); a *bought* ingredient
  contributes none, because you paid its maker for that labor. So the whole
  tree's labor is already inside the rolled-up ingredient cost, while a recipe's
  own `laborCost` / `laborCalories` lines report **its** marginal labor step.
- **Time.** `craftMinutes` roll up the same way and monetize at `minutePrice`.

### Why `caloriePrice` / `minutePrice` default to 0

eco-app has no server-agnostic feed for "what a calorie costs" (it depends on the
cheapest food a player farms) or "what a minute of crafting is worth" - those are
per-server, per-player policy inputs. So the engine **always reports the raw
calorie and minute totals** and only folds them into the currency figure when the
caller supplies a rate. The default keeps the money number to the part we can
defend from real trade data (ingredients); D and E can pass a server-tuned rate.
The chosen rate rides back on the payload as `costParams` so a consumer can see
exactly what the numbers assume.

## The DTO

`rollup_recipe(index, recipeName, prices, params)` returns a `RecipeCost`; its
`to_dict()` is the `cost` object attached to each recipe row:

```
cost {
  recipe, product, yield,
  perUnitCost,          # total / yield, or null when incomplete
  totalCost,            # ingredientCost + laborCost + timeCost
  ingredientCost,       # Σ ingredient lines (each bundles its own sub-tree)
  laborCost,            # this recipe's laborCalories * caloriePrice
  timeCost,             # this recipe's craftMinutes * minutePrice
  laborCalories,        # this recipe's own labor (raw), always present
  craftMinutes,         # this recipe's own time (raw), always present
  complete,             # false if any leaf under it is unpriced
  unpricedInputs [ itemId, ... ],
  ingredients [ { item, displayName, quantity, isTag,
                  unitCost, source, subtotal }, ... ],
}
```

The ingredient line `source` is `market` (bought), `craft` (rolled up from its
own recipe), or `unpriced`. Line subtotals sum to `ingredientCost`; `totalCost`
adds this recipe's own labor and time on top - so the money is fully recursive
(a crafted sub-ingredient's own labor is inside its make-or-buy `unitCost`) while
the labor/time lines describe just the visible step.

## Resolution rules

- **Variants.** An item with several producing recipes (same `FamilyName` or
  otherwise) is costed by whichever recipe is cheapest, evaluated through the
  same make-or-buy comparison.
- **Tags / categories.** A tag ingredient (`isTag`) resolves to its **cheapest**
  member from `RecipeIndex.tags`; if no member is priced the tag itself is the
  `unpricedInputs` entry, so the surface names the category, not an arbitrary
  member.
- **Cycles.** Eco's graph is mostly acyclic but has loops (waste → reclaim). A
  recipe that would recurse into an item already on the craft stack drops that
  path for that node, which then falls back to market or unpriced - so the
  roll-up terminates instead of recursing forever.
- **Incomplete beats misleading.** When a make-or-buy choice weighs a partially
  priced craft path against a real market price, the fully-priced candidate wins
  outright (an incomplete path understates its cost, so comparing by money alone
  would spuriously favour it).

## Surface

`/preview/recipes.json?cost=1` turns on the roll-up: every recipe row gains the
`cost` field above, and a top-level `costParams` echoes the rate used. Without
`?cost=1` the route is the plain bill-of-materials plane (no market fetch), so
callers that only want the BOM pay nothing.

- `?server=` - which server's market to price against (leaf prices come from its
  live trades ledger, via `market.fetch_price_map`, an **uncapped**
  `fetch_market` flattened to one median per item).
- `?caloriePrice=` / `?minutePrice=` - monetize the labor / time axes.
- `?product=` / `?skill=` / `?station=` - narrow the returned rows (the roll-up
  still recurses over the whole graph via the intact lookup maps).

An unreachable market **degrades**: the roll-up still ships, every leaf just
reads "unpriced", `complete` is false, and a `warnings` note says the prices were
unavailable - the page renders "cost unavailable / partial" instead of a wrong
zero.

## Purity and testing

`rollup_recipe` / `annotate_payload` take a plain `prices` mapping and a
`CostParams`, so the cost math unit-tests with a hand-written dict - no market
fetch, no HTTP (`tests/mcp/test_cost.py`). The `/preview` route is the only place
that reaches for the live market, and its tests monkeypatch `fetch_price_map` to
stay offline.

## Known simplifications (follow-ups)

- **Byproducts are not credited** against the primary product's cost yet, so a
  recipe that yields a valuable secondary reads as a conservative over-estimate.
  Crediting them needs a priced byproduct and a split rule - deferred, tracked on
  [#98](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/98).
- **Baseline recipes only.** Costs use `recipes._base_value` quantities, ignoring
  per-player skill/talent/module efficiency - the same deliberate baseline the
  BOM seed takes. A per-player overlay is a later concern.
- **`caloriePrice` is a manual input.** Deriving a default from the cheapest food
  on a given server (the way Eco Gnome does) would make the money figure whole by
  default; it needs a food-item price feed and is left for D/E.

## See also

- [docs/FEATURES.md](FEATURES.md) - where this sits in the inventory.
- [docs/recipes.md](recipes.md) - the bill-of-materials this rolls up (A).
- [docs/trades.md](trades.md) - the ledger the market medians derive from.
- [#98](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/98) - the roadmap epic; [#102](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/102) - this ticket.
