"""Tests for the bottom-up cost roll-up engine (eco-app#102, follow-up C).

Covers:
  - A single recipe costs = ingredient market prices + own labor/time.
  - Make-or-buy: a crafted sub-ingredient rolls up recursively, and the engine
    picks the cheaper of crafting vs buying it at market.
  - A multi-level tree (ore → bar → steel) rolls the whole chain up.
  - An unpriced leaf surfaces as an `unpricedInputs` entry with `complete=False`
    and a `None` per-unit cost — never silently zeroed.
  - Category/tag inputs resolve to their cheapest member.
  - Cycles (A needs B, B needs A) terminate instead of recursing forever.
  - Labor calories / craft minutes monetize at the supplied CostParams.
  - `annotate_payload` attaches a `cost` field to a serialized index payload,
    honoring a `filter_index` narrowing while still recursing over the whole
    graph.
  - `market.price_map` collapses per-currency markets to one price per item.
  - `/preview/recipes.json?cost=1` serves the roll-up and degrades to
    all-unpriced when the market is unreachable.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from eco_mcp_app import recipes as recipes_mod
from eco_mcp_app.cost import CostParams, annotate_payload, rollup_recipe
from eco_mcp_app.market import build_market, price_map
from eco_mcp_app.recipes import build_recipe_index, filter_index

# A synthetic recipe graph exercising every branch of the engine:
#   IronOreItem, CoalItem, CharcoalItem   -> raw leaves (market-priced)
#   ScrapItem                             -> raw leaf (expensive, so craft wins)
#   WaterItem                             -> raw leaf, deliberately UNPRICED
#   IronBarItem <- ore + coal | scrap     -> intermediate, two recipes (variants)
#   SteelItem   <- bar + coal             -> multi-level product
#   GearItem    <- bar + water            -> product with an unpriced leaf
#   AshItem     <- 2x Fuel (a tag)        -> tag/category input
#   AItem <-> BItem                       -> a cycle
_RAW = {
    "Version": 1,
    "Tags": [
        {"Name": "Fuel", "AssociatedItems": ["CoalItem", "CharcoalItem"]},
    ],
    "Recipes": [
        {
            "Name": "IronBarRecipe",
            "FamilyName": "IronBar",
            "Labor": {"BaseValue": 100.0},
            "CraftMinutes": {"BaseValue": 1.0},
            "CraftingTable": "SmelterItem",
            "Ingredients": [
                {"ItemOrTag": "IronOreItem", "Quantity": {"BaseValue": 3.0}},
                {"ItemOrTag": "CoalItem", "Quantity": {"BaseValue": 1.0}},
            ],
            "Products": [{"ItemOrTag": "IronBarItem", "Quantity": {"BaseValue": 2.0}}],
        },
        {
            # Alternate way to make a bar — from scrap. Priced so it loses the
            # make-or-buy race to the ore recipe (proves variant selection).
            "Name": "IronBarScrapRecipe",
            "FamilyName": "IronBar",
            "Labor": {"BaseValue": 10.0},
            "CraftMinutes": {"BaseValue": 0.5},
            "CraftingTable": "SmelterItem",
            "Ingredients": [{"ItemOrTag": "ScrapItem", "Quantity": {"BaseValue": 5.0}}],
            "Products": [{"ItemOrTag": "IronBarItem", "Quantity": {"BaseValue": 1.0}}],
        },
        {
            "Name": "SteelRecipe",
            "FamilyName": "Steel",
            "Labor": {"BaseValue": 200.0},
            "CraftMinutes": {"BaseValue": 2.0},
            "CraftingTable": "SmelterItem",
            "Ingredients": [
                {"ItemOrTag": "IronBarItem", "Quantity": {"BaseValue": 2.0}},
                {"ItemOrTag": "CoalItem", "Quantity": {"BaseValue": 3.0}},
            ],
            "Products": [{"ItemOrTag": "SteelItem", "Quantity": {"BaseValue": 1.0}}],
        },
        {
            "Name": "GearRecipe",
            "FamilyName": "Gear",
            "Labor": {"BaseValue": 50.0},
            "CraftMinutes": {"BaseValue": 1.0},
            "CraftingTable": "MachinistTableItem",
            "Ingredients": [
                {"ItemOrTag": "IronBarItem", "Quantity": {"BaseValue": 1.0}},
                {"ItemOrTag": "WaterItem", "Quantity": {"BaseValue": 1.0}},
            ],
            "Products": [{"ItemOrTag": "GearItem", "Quantity": {"BaseValue": 1.0}}],
        },
        {
            "Name": "AshRecipe",
            "FamilyName": "Ash",
            "Labor": {"BaseValue": 0.0},
            "CraftMinutes": {"BaseValue": 0.0},
            "CraftingTable": "CampfireItem",
            "Ingredients": [{"ItemOrTag": "Fuel", "Quantity": {"BaseValue": 2.0}}],
            "Products": [{"ItemOrTag": "AshItem", "Quantity": {"BaseValue": 1.0}}],
        },
        {
            "Name": "ARecipe",
            "FamilyName": "A",
            "CraftingTable": "T",
            "Ingredients": [{"ItemOrTag": "BItem", "Quantity": {"BaseValue": 1.0}}],
            "Products": [{"ItemOrTag": "AItem", "Quantity": {"BaseValue": 1.0}}],
        },
        {
            "Name": "BRecipe",
            "FamilyName": "B",
            "CraftingTable": "T",
            "Ingredients": [{"ItemOrTag": "AItem", "Quantity": {"BaseValue": 1.0}}],
            "Products": [{"ItemOrTag": "BItem", "Quantity": {"BaseValue": 1.0}}],
        },
    ],
}

# Market medians for the raw leaves. Note: no WaterItem (unpriced) and no
# IronBarItem (so the intermediate is crafted, not bought).
_PRICES = {
    "IronOreItem": 2.0,
    "CoalItem": 5.0,
    "CharcoalItem": 8.0,
    "ScrapItem": 100.0,
}


@pytest.fixture
def index() -> recipes_mod.RecipeIndex:
    return build_recipe_index(_RAW)


def test_intermediate_rolls_up_recursively(index: recipes_mod.RecipeIndex) -> None:
    # A bar: (3 ore x2 + 1 coal x5) / 2 produced = 11/2 = 5.5, labor/time free.
    cost = rollup_recipe(index, "IronBarRecipe", _PRICES)
    assert cost is not None
    assert cost.complete is True
    assert cost.per_unit_cost == pytest.approx(5.5)
    assert cost.ingredient_cost == pytest.approx(11.0)
    assert {line.item for line in cost.ingredients} == {"IronOreItem", "CoalItem"}


def test_multi_level_tree(index: recipes_mod.RecipeIndex) -> None:
    # Steel needs 2 bars + 3 coal. Bar rolls up to 5.5 each (cheaper to craft
    # than the 100-scrap variant), coal is 5 at market.
    cost = rollup_recipe(index, "SteelRecipe", _PRICES)
    assert cost is not None
    assert cost.complete is True
    # ingredientCost = 2*5.5 + 3*5 = 26; labor/time free at default params.
    assert cost.ingredient_cost == pytest.approx(26.0)
    assert cost.per_unit_cost == pytest.approx(26.0)
    bar_line = next(line for line in cost.ingredients if line.item == "IronBarItem")
    assert bar_line.source == "craft"
    assert bar_line.unit_cost == pytest.approx(5.5)


def test_make_or_buy_prefers_cheaper_market(index: recipes_mod.RecipeIndex) -> None:
    # When the bar trades below its craft cost, Steel buys it instead of crafting.
    prices = {**_PRICES, "IronBarItem": 3.0}
    cost = rollup_recipe(index, "SteelRecipe", prices)
    assert cost is not None
    bar_line = next(line for line in cost.ingredients if line.item == "IronBarItem")
    assert bar_line.source == "market"
    assert bar_line.unit_cost == pytest.approx(3.0)
    assert cost.ingredient_cost == pytest.approx(2 * 3.0 + 3 * 5.0)


def test_unpriced_leaf_is_surfaced_not_zeroed(index: recipes_mod.RecipeIndex) -> None:
    cost = rollup_recipe(index, "GearRecipe", _PRICES)
    assert cost is not None
    assert cost.complete is False
    assert cost.per_unit_cost is None  # not a misleading partial number
    assert cost.unpriced_inputs == ["WaterItem"]
    water_line = next(line for line in cost.ingredients if line.item == "WaterItem")
    assert water_line.source == "unpriced"
    assert water_line.unit_cost is None and water_line.subtotal is None
    # The priced part of the BOM still shows through.
    bar_line = next(line for line in cost.ingredients if line.item == "IronBarItem")
    assert bar_line.subtotal == pytest.approx(5.5)


def test_tag_input_resolves_to_cheapest_member(index: recipes_mod.RecipeIndex) -> None:
    # Fuel = {Coal 5, Charcoal 8} → cheapest is Coal at 5; recipe uses 2.
    cost = rollup_recipe(index, "AshRecipe", _PRICES)
    assert cost is not None
    assert cost.complete is True
    assert cost.ingredient_cost == pytest.approx(10.0)
    fuel_line = next(line for line in cost.ingredients if line.item == "Fuel")
    assert fuel_line.is_tag is True
    assert fuel_line.unit_cost == pytest.approx(5.0)


def test_cycle_terminates(index: recipes_mod.RecipeIndex) -> None:
    # A <-> B with no market price for either: must not recurse forever, and
    # must report the cycle as unpriced rather than hanging.
    cost = rollup_recipe(index, "ARecipe", _PRICES)
    assert cost is not None
    assert cost.complete is False
    assert "BItem" in cost.unpriced_inputs or "AItem" in cost.unpriced_inputs


def test_labor_and_time_monetize(index: recipes_mod.RecipeIndex) -> None:
    params = CostParams(calorie_cost=0.1, minute_cost=1.0)
    # Bar now costs (6 + 5 + 100*0.1 + 1*1.0) / 2 = 22/2 = 11 each.
    bar = rollup_recipe(index, "IronBarRecipe", _PRICES, params)
    assert bar is not None
    assert bar.per_unit_cost == pytest.approx(11.0)
    assert bar.labor_cost == pytest.approx(10.0)  # 100 cal * 0.1
    assert bar.time_cost == pytest.approx(1.0)  # 1 min * 1.0
    assert bar.labor_calories == pytest.approx(100.0)  # own recipe, raw

    steel = rollup_recipe(index, "SteelRecipe", _PRICES, params)
    assert steel is not None
    # ingredientCost = 2*11 + 3*5 = 37; labor 200*0.1 = 20; time 2*1 = 2 → 59.
    assert steel.ingredient_cost == pytest.approx(37.0)
    assert steel.per_unit_cost == pytest.approx(59.0)


def test_unknown_recipe_returns_none(index: recipes_mod.RecipeIndex) -> None:
    assert rollup_recipe(index, "NopeRecipe", _PRICES) is None


# ---------- annotate_payload ----------


def test_annotate_payload_adds_cost_field(index: recipes_mod.RecipeIndex) -> None:
    payload = filter_index(index)  # full graph
    annotate_payload(payload, index, _PRICES, CostParams(calorie_cost=0.1))
    assert payload["costParams"] == {"caloriePrice": 0.1, "minutePrice": 0.0}
    steel = next(r for r in payload["recipes"] if r["name"] == "SteelRecipe")
    assert steel["cost"]["complete"] is True
    assert steel["cost"]["perUnitCost"] is not None
    assert steel["cost"]["ingredients"][0]["item"] in {"IronBarItem", "CoalItem"}


def test_annotate_payload_honors_filter_but_recurses_full_graph(
    index: recipes_mod.RecipeIndex,
) -> None:
    # Narrow to just Steel; the roll-up must still recurse into IronBar (which
    # is no longer in the `recipes` list) via the intact lookup maps.
    payload = filter_index(index, product="SteelItem")
    annotate_payload(payload, index, _PRICES)
    assert {r["name"] for r in payload["recipes"]} == {"SteelRecipe"}
    steel = payload["recipes"][0]
    assert steel["cost"]["complete"] is True
    assert steel["cost"]["ingredientCost"] == pytest.approx(26.0)


# ---------- market.price_map ----------


def test_price_map_keeps_busiest_market_per_item() -> None:
    rows = [
        {"item": "WoodItem", "currency": "Credit", "day": 1, "unitPrice": 10.0, "quantity": 1},
        {"item": "WoodItem", "currency": "Credit", "day": 1, "unitPrice": 12.0, "quantity": 1},
        # A thinner Gold market for the same item — should lose to Credit.
        {"item": "WoodItem", "currency": "Gold", "day": 1, "unitPrice": 99.0, "quantity": 1},
    ]
    markets = build_market(rows)
    prices = price_map(markets)
    assert set(prices) == {"WoodItem"}
    assert prices["WoodItem"] == pytest.approx(11.0)  # median(10,12) from Credit


# ---------- /preview/recipes.json?cost=1 route ----------


def _make_client() -> TestClient:
    from eco_mcp_app.http_app import create_app

    return TestClient(create_app())


def test_preview_recipes_cost_off_by_default() -> None:
    # No ?cost=1 → no market fetch, no cost field (the plain BOM plane).
    client = _make_client()
    r = client.get("/preview/recipes.json")
    assert r.status_code == 200
    payload = r.json()
    assert "costParams" not in payload
    assert all("cost" not in row for row in payload["recipes"][:5])


def test_preview_recipes_cost_on_with_mocked_market(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_price_map(*args: object, **kwargs: object) -> dict[str, float]:
        return {}

    # The cost engine moved behind the price_recipe tool (eco-app#242), so the
    # market read now happens in the market module the tool reaches through.
    monkeypatch.setattr("eco_mcp_app.market.fetch_price_map", _fake_price_map)
    client = _make_client()
    r = client.get("/preview/recipes.json", params={"cost": "1"})
    assert r.status_code == 200
    payload = r.json()
    assert payload["costParams"] == {"caloriePrice": 0.0, "minutePrice": 0.0}
    # Every recipe row gains a cost field; with an empty price map any recipe
    # that consumes a material reads unpriced (most of the ~1,450 graph).
    assert all("cost" in row for row in payload["recipes"])
    assert any(row["cost"]["complete"] is False for row in payload["recipes"])


def test_preview_recipes_cost_degrades_when_market_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _boom(*args: object, **kwargs: object) -> dict[str, float]:
        raise httpx.ConnectError("no route to exporter")

    monkeypatch.setattr("eco_mcp_app.market.fetch_price_map", _boom)
    client = _make_client()
    r = client.get("/preview/recipes.json", params={"cost": "1"})
    assert r.status_code == 200
    payload = r.json()
    assert any("market unreachable" in w for w in payload["warnings"])
    assert "cost" in payload["recipes"][0]


def test_an_incomplete_rollup_reports_no_total_rather_than_zero() -> None:
    """A partial sum is not a cost. Reporting 0 made the recipe where nothing
    priced look 7x cheaper than the ones that did. See #266."""
    from eco_mcp_app.cost import RecipeCost

    rollup = RecipeCost(
        recipe="RecycledIronBar",
        product="IronBarItem",
        yield_qty=1,
        per_unit_cost=None,
        total_cost=0.22,
        ingredient_cost=0.0,
        labor_cost=0.22,
        time_cost=0.0,
        labor_calories=0.0,
        craft_minutes=0.0,
        complete=False,
        unpriced_inputs=["ScrapIronItem", "CharcoalItem"],
        ingredients=[],
    )
    payload = rollup.to_dict()
    assert payload["totalCost"] is None
    assert payload["ingredientCost"] is None
    # The evidence a caller needs to act is still there.
    assert payload["unpricedInputs"] == ["ScrapIronItem", "CharcoalItem"]
    assert payload["complete"] is False


def test_a_complete_rollup_still_reports_its_numbers() -> None:
    """The distinction that must survive: unpriced is not the same as free."""
    from eco_mcp_app.cost import RecipeCost

    rollup = RecipeCost(
        recipe="SmeltIron",
        product="IronBarItem",
        yield_qty=1,
        per_unit_cost=3.18,
        total_cost=3.18,
        ingredient_cost=2.56,
        labor_cost=0.62,
        time_cost=0.0,
        labor_calories=0.0,
        craft_minutes=0.0,
        complete=True,
        unpriced_inputs=[],
        ingredients=[],
    )
    payload = rollup.to_dict()
    assert payload["totalCost"] == 3.18
    assert payload["ingredientCost"] == 2.56
