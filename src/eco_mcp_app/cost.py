"""Bottom-up cost roll-up engine — recipe BOM → per-item cost / margin.

`recipes.py` (eco-app#100, follow-up **A**) gives eco-app the bill-of-materials
it was missing: ingredients-in / product-out, station, required skill, labor
(calories) and craft time. `market.py` (eco-app#49) gives the *other* half — a
per-item median trade price. This module is follow-up **C** on the #98 roadmap:
it fuses the two into the number every downstream page needs, a **cost to craft
one unit**, so margin ("`medianUnitPrice - rolledUpCost`") and "is this worth
crafting" finally become answerable.

The model (bottom-up, recursive over the ingredient edges A exposes):

* **Ingredient cost.** For each ingredient the engine takes the *cheaper* of
  buying it at market median or crafting it from its own recipe — the classic
  make-or-buy decision. Following that decision recursively rolls the whole
  dependency tree up from raw leaves. A **leaf** (a raw resource with no
  producing recipe) is priced at its market median; a leaf with *no* market
  price is surfaced as an **unpriced input**, never silently zeroed.
* **Labor + calories.** Eco meters labor in **calories**. Every recipe the
  engine actually crafts folds its labor calories into that node's money at a
  caller-supplied `calorie_cost` (currency per calorie); a *bought* ingredient
  contributes none — you paid its maker for the labor. So the whole tree's labor
  is already inside the rolled-up ingredient cost, while the top card's
  `laborCost` / `laborCalories` lines report *this* recipe's own labor (the
  marginal step). The raw calorie figure is always present so the labor axis is
  visible even when `calorie_cost` is 0.
* **Time.** Craft minutes roll up the same way and monetize at `minute_cost`
  (default 0 — time is reported, priced only if the caller sets a rate).

Design posture, matching the rest of the package:

* **Pure, no I/O.** `rollup_recipe` / `annotate_payload` take a plain `prices`
  mapping and a `CostParams`, so the cost math unit-tests with a hand-written
  dict — no market fetch, no HTTP. The `/preview/recipes.json` route builds the
  price map from `market.py` and hands it in.
* **Graceful degradation.** An unreachable market → an empty price map → every
  leaf reads "unpriced", `complete=False`, and the labor/time axes still roll up.
  The page renders "cost unavailable / partial" instead of a wrong zero.
* **Cycle-guarded.** Eco's graph is mostly acyclic but has loops (waste →
  reclaim). A recipe that would recurse into an item already on the craft stack
  is skipped for that node, so the node falls back to market (or unpriced)
  rather than recursing forever.

Cost is a heuristic, not an oracle: byproducts are not yet credited against the
primary product's cost (a conservative over-estimate — see eco-app#98), and the
make-or-buy choice uses the *baseline* recipe (no per-player skill/module
discounts, per `recipes._base_value`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .crafting import prettify_eco_name
from .recipes import Recipe, RecipeIndex

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CostParams:
    """Monetization knobs for the non-ingredient cost axes.

    Both default to 0: eco-app has no server-agnostic feed for "what a calorie
    costs" (it depends on the cheapest food a player farms) or "what a minute of
    crafting is worth", so the engine reports the raw calorie / minute totals
    unconditionally and only folds them into the currency total when the caller
    supplies a rate. The pricing page (E) / value-per-profession page (D) can
    pass a server-tuned rate; the default keeps the money figure to the part we
    can defend from real trade data (ingredients).
    """

    calorie_cost: float = 0.0  # currency per labor calorie
    minute_cost: float = 0.0  # currency per craft minute

    def to_dict(self) -> dict[str, Any]:
        return {"caloriePrice": self.calorie_cost, "minutePrice": self.minute_cost}


# ---------------------------------------------------------------------------
# Node-level roll-up result (internal + serialized)
# ---------------------------------------------------------------------------


@dataclass
class NodeCost:
    """Resolved cost of one unit of an item (or one craft of a recipe).

    `money` is the fully-monetized unit cost: for a crafted node it already
    bundles the whole sub-tree — every raw material plus every sub-recipe's
    labor and time, monetized at the run's `CostParams`. That is what lets a
    parent treat a crafted ingredient exactly like a bought one (a single price)
    and lets the make-or-buy pick compare the two by `money` alone. When
    `complete` is False some leaf under this node had no market price, so
    `money` is a lower bound and `unpriced` names the offending inputs.
    """

    money: float
    complete: bool
    source: str  # "market" | "craft" | "unpriced"
    unpriced: list[str] = field(default_factory=list)


def _normalize(item: str) -> str:
    """Fold an item id to a price-map key: lowercase, drop a trailing `item`.

    Mirrors `market._normalize_item` so a recipe's `ShaleItem` finds a market
    keyed on either `ShaleItem` or `Shale` without a hand-maintained alias table.
    """
    stem = (item or "").strip().lower()
    if stem.endswith("item") and len(stem) > len("item"):
        stem = stem[: -len("item")]
    return stem


class _Resolver:
    """Recursive make-or-buy solver over a `RecipeIndex` + price map.

    Memoizes per item id. A `_stack` set breaks cycles: an item reached while
    already being resolved cannot be crafted as part of itself, so that craft
    path is dropped and the node falls back to market / unpriced.
    """

    def __init__(self, index: RecipeIndex, prices: Mapping[str, float], params: CostParams) -> None:
        self._index = index
        self._params = params
        # Exact-id map plus a normalized fallback, so both `ShaleItem` and the
        # market's `Shale` resolve. Exact wins on collision.
        self._exact = dict(prices)
        self._norm: dict[str, float] = {}
        for k, v in prices.items():
            self._norm.setdefault(_normalize(k), v)
        self._by_name = {r.name: r for r in index.recipes}
        self._memo: dict[str, NodeCost] = {}
        self._stack: set[str] = set()

    # -- price lookups --

    def _market_price(self, item: str) -> float | None:
        if item in self._exact:
            return self._exact[item]
        return self._norm.get(_normalize(item))

    def _recipes_for(self, item: str) -> list[Recipe]:
        names = self._index.by_product.get(item, [])
        return [self._by_name[n] for n in names if n in self._by_name]

    def _tag_members(self, tag: str) -> list[str]:
        return list(self._index.tags.get(tag, []))

    # -- core recursion --

    def item_cost(self, item: str) -> NodeCost:
        """Cheapest resolved cost of one unit of `item` (make-or-buy)."""
        cached = self._memo.get(item)
        if cached is not None:
            return cached
        if item in self._stack:
            # Cycle: resolve this occurrence as a leaf (market or unpriced)
            # without recursing or memoizing — the memo is written by the
            # top-of-cycle frame once it finishes.
            return self._leaf_cost(item)

        # A tag ingredient resolves to the cheapest of its members.
        if item in self._index.tags and item not in self._exact:
            result = self._tag_cost(item)
            self._memo[item] = result
            return result

        candidates: list[NodeCost] = []
        market = self._market_price(item)
        if market is not None:
            candidates.append(NodeCost(money=market, complete=True, source="market"))

        self._stack.add(item)
        for recipe in self._recipes_for(item):
            candidates.append(self._craft_cost(recipe))
        self._stack.discard(item)

        result = self._pick(candidates) or self._leaf_cost(item)
        self._memo[item] = result
        return result

    def _leaf_cost(self, item: str) -> NodeCost:
        """A raw / un-craftable node: market price if any, else unpriced."""
        market = self._market_price(item)
        if market is not None:
            return NodeCost(money=market, complete=True, source="market")
        return NodeCost(money=0.0, complete=False, source="unpriced", unpriced=[item])

    def _tag_cost(self, tag: str) -> NodeCost:
        """Resolve a category/tag input to its cheapest member item."""
        members = [self.item_cost(m) for m in self._tag_members(tag)]
        priced = [m for m in members if m.complete]
        if priced:
            return min(priced, key=lambda n: n.money)
        if members:
            # No member is fully priced: keep the least-bad (fewest unpriced),
            # but re-key the unpriced note to the tag so the surface names the
            # category, not an arbitrary member.
            best = min(members, key=lambda n: (len(n.unpriced), n.money))
            return NodeCost(money=best.money, complete=False, source=best.source, unpriced=[tag])
        return NodeCost(money=0.0, complete=False, source="unpriced", unpriced=[tag])

    def _craft_cost(self, recipe: Recipe) -> NodeCost:
        """Fully-monetized cost of one unit of `recipe`'s product by crafting it.

        Bundles every ingredient's make-or-buy cost (recursively) plus this
        recipe's own labor and time, monetized at the run's `CostParams`, then
        divides by the product yield. A crafted sub-ingredient thus arrives as a
        single `money` figure the parent adds like any bought input.
        """
        qty_out = recipe.product.quantity or 1.0
        money = recipe.labor_cost * self._params.calorie_cost
        money += recipe.craft_minutes * self._params.minute_cost
        complete = True
        unpriced: list[str] = []
        for ing in recipe.ingredients:
            node = self.item_cost(ing.item)
            money += node.money * ing.quantity
            if not node.complete:
                complete = False
                unpriced.extend(node.unpriced)
        return NodeCost(
            money=money / qty_out,
            complete=complete,
            source="craft",
            unpriced=_dedupe(unpriced),
        )

    @staticmethod
    def _pick(candidates: list[NodeCost]) -> NodeCost | None:
        """Choose the make-or-buy winner: cheapest fully-priced, else least-bad.

        Comparing an incomplete craft path (its money understates because a leaf
        is unpriced) against a real market price by money alone would spuriously
        favour the incomplete path, so complete candidates win outright; only
        when none is complete do we fall back to fewest-unpriced then cheapest.
        """
        if not candidates:
            return None
        complete = [c for c in candidates if c.complete]
        if complete:
            return min(complete, key=lambda n: n.money)
        return min(candidates, key=lambda n: (len(n.unpriced), n.money))


def _dedupe(items: list[str]) -> list[str]:
    """Order-preserving de-dupe (an item can be unpriced via several edges)."""
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


# ---------------------------------------------------------------------------
# Recipe-level roll-up (the serialized `cost` field)
# ---------------------------------------------------------------------------


@dataclass
class IngredientCost:
    """One ingredient line of a recipe's cost breakdown."""

    item: str
    display_name: str
    quantity: float
    is_tag: bool
    unit_cost: float | None  # None ⇒ unpriced
    source: str
    subtotal: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "item": self.item,
            "displayName": self.display_name,
            "quantity": self.quantity,
            "isTag": self.is_tag,
            "unitCost": self.unit_cost,
            "source": self.source,
            "subtotal": self.subtotal,
        }


@dataclass
class RecipeCost:
    """The rolled-up cost of one recipe — the `cost` field of a recipe row."""

    recipe: str
    product: str
    yield_qty: float
    per_unit_cost: float | None
    total_cost: float
    ingredient_cost: float
    labor_cost: float
    time_cost: float
    labor_calories: float
    craft_minutes: float
    complete: bool
    unpriced_inputs: list[str]
    ingredients: list[IngredientCost]

    def to_dict(self) -> dict[str, Any]:
        return {
            "recipe": self.recipe,
            "product": self.product,
            "yield": self.yield_qty,
            "perUnitCost": self.per_unit_cost,
            "totalCost": self.total_cost,
            "ingredientCost": self.ingredient_cost,
            "laborCost": self.labor_cost,
            "timeCost": self.time_cost,
            "laborCalories": self.labor_calories,
            "craftMinutes": self.craft_minutes,
            "complete": self.complete,
            "unpricedInputs": list(self.unpriced_inputs),
            "ingredients": [i.to_dict() for i in self.ingredients],
        }


def _rollup(resolver: _Resolver, recipe: Recipe, params: CostParams) -> RecipeCost:
    """Cost the given recipe (always crafted — it *is* the question) into the
    serialized `cost` breakdown, its ingredients resolved make-or-buy underneath.

    The money splits three ways: `ingredient_cost` (the sum of the direct
    ingredient lines, each already bundling that ingredient's own sub-tree via
    its make-or-buy price), plus this recipe's own `labor_cost` and `time_cost`.
    `total = ingredient_cost + labor_cost + time_cost` is therefore fully
    recursive in money terms; `labor_calories` / `craft_minutes` report *this*
    recipe's own labor, the axes the `labor_cost` / `time_cost` lines monetize.
    """
    qty_out = recipe.product.quantity or 1.0
    ingredient_total = 0.0
    complete = True
    unpriced: list[str] = []
    lines: list[IngredientCost] = []
    for ing in recipe.ingredients:
        node = resolver.item_cost(ing.item)
        subtotal = node.money * ing.quantity if node.complete else None
        if subtotal is not None:
            ingredient_total += subtotal
        else:
            complete = False
            unpriced.extend(node.unpriced)
        lines.append(
            IngredientCost(
                item=ing.item,
                display_name=prettify_eco_name(ing.item) if not ing.is_tag else ing.item,
                quantity=ing.quantity,
                is_tag=ing.is_tag,
                unit_cost=node.money if node.complete else None,
                source=node.source,
                subtotal=subtotal,
            )
        )

    labor_cost = recipe.labor_cost * params.calorie_cost
    time_cost = recipe.craft_minutes * params.minute_cost
    total = ingredient_total + labor_cost + time_cost
    return RecipeCost(
        recipe=recipe.name,
        product=recipe.product.item,
        yield_qty=qty_out,
        per_unit_cost=(total / qty_out) if complete else None,
        total_cost=total,
        ingredient_cost=ingredient_total,
        labor_cost=labor_cost,
        time_cost=time_cost,
        labor_calories=recipe.labor_cost,
        craft_minutes=recipe.craft_minutes,
        complete=complete,
        unpriced_inputs=_dedupe(unpriced),
        ingredients=lines,
    )


def rollup_recipe(
    index: RecipeIndex,
    recipe_name: str,
    prices: Mapping[str, float],
    params: CostParams | None = None,
) -> RecipeCost | None:
    """Roll up the cost of a single recipe by name. None if unknown."""
    params = params or CostParams()
    recipe = next((r for r in index.recipes if r.name == recipe_name), None)
    if recipe is None:
        return None
    return _rollup(_Resolver(index, prices, params), recipe, params)


def annotate_payload(
    payload: dict[str, Any],
    index: RecipeIndex,
    prices: Mapping[str, float],
    params: CostParams | None = None,
) -> dict[str, Any]:
    """Attach a `cost` object to every recipe row of a serialized index payload.

    Mutates and returns `payload` (a `RecipeIndex.to_dict()` / `filter_index`
    result). `index` is the *unfiltered* `RecipeIndex` the payload came from —
    the make-or-buy recursion needs the whole craft graph even when the page
    asked for a single product's rows (`filter_index` narrows `recipes` but
    keeps the lookup maps whole for exactly this reason). One shared `_Resolver`
    memoizes across the graph, so the ~1,450-recipe roll-up stays close to
    linear. Adds a top-level `costParams` echo so a consumer can see the
    calorie/minute rate the numbers assume.
    """
    params = params or CostParams()
    resolver = _Resolver(index, prices, params)
    by_name = {r.name: r for r in index.recipes}
    for row in payload.get("recipes", []):
        recipe = by_name.get(row.get("name"))
        if recipe is None:
            continue
        row["cost"] = _rollup(resolver, recipe, params).to_dict()
    payload["costParams"] = params.to_dict()
    return payload
