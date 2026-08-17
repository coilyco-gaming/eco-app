# The cost model

What an item costs to make, derived from recipes and live market prices.
Inputs are `recipes.py` (#100) for the recipe graph and `market.py` (#49) for
observed prices.

## The model

- **Ingredient cost, make-or-buy.** For each ingredient the engine takes the
  cheaper of making it and buying it, recursively.
- **Labor and calories.** Eco meters labor in calories. Every recipe's calorie
  cost monetizes at `caloriePrice`.
- **Time.** `craftMinutes` roll up the same way and monetize at `minutePrice`.

`caloriePrice` and `minutePrice` default to **0** so the model reports pure
material cost unless an operator states what their time and food are worth.
A non-zero default would be a made-up number appearing in every answer.

## Resolution rules

- **Variants.** An item with several producing recipes, sharing a `FamilyName`,
  resolves to the cheapest.
- **Tags.** A tag ingredient (`isTag`) resolves to its cheapest member.
- **Cycles.** Eco's graph is mostly acyclic but has loops, such as waste into
  reclaim. A cycle is broken rather than followed.
- **Incomplete beats misleading.** When a make-or-buy choice rests on a
  partially-priced branch, the engine reports incompleteness rather than
  quietly picking the side it happens to have numbers for.

**Purity.** The engine is pure over its inputs, so the tests supply a recipe
graph and a price table and assert the cost, with no network.

## Known simplifications

Byproducts are not yet credited against the primary product's cost, so a recipe
producing something useful alongside its product reads as more expensive than
it is. Costs use `recipes._base_value` baseline quantities, ignoring modifiers.
`caloriePrice` stays a manual input.

See also: [recipes.md](recipes.md), [price-history.md](price-history.md).
