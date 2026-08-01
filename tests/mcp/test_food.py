"""Food restock signals stay bounded to positively identified recipe products."""

import pytest

from eco_mcp_app.food import FoodReport, build_food_report, food_product_ids
from eco_mcp_app.http_app import create_app
from eco_mcp_app.items import ItemIndex
from eco_mcp_app.logistics import LogisticsReport
from eco_mcp_app.recipes import Recipe, RecipeComponent, RecipeIndex
from starlette.testclient import TestClient


def _recipes() -> RecipeIndex:
    return RecipeIndex(
        fetched_at_iso="2026-08-01T00:00:00+00:00",
        source="fixture",
        recipes=[
            Recipe(
                name="CookedCorn",
                display_name="Cooked Corn",
                product=RecipeComponent(item="CookedCornItem", quantity=1),
                skill_name="ChefSkill",
            ),
            Recipe(
                name="IronBar",
                display_name="Iron Bar",
                product=RecipeComponent(item="IronBarItem", quantity=1),
                skill_name="SmeltingSkill",
            ),
        ],
    )


def _items() -> ItemIndex:
    return ItemIndex(
        fetched_at_iso="2026-08-01T00:00:00+00:00",
        source_base_url="http://eco.example",
        items=[
            {"item": "CookedCornItem", "tradeCount": 4, "tradeVolume": 20, "craftCount": 10},
            {"item": "IronBarItem", "tradeCount": 4, "tradeVolume": 20, "craftCount": 10},
        ],
    )


def test_food_products_only_include_confirmed_cooking_recipe_outputs() -> None:
    assert food_product_ids(_recipes()) == {"CookedCornItem"}


def test_food_report_marks_live_supply_gap_restock_and_excludes_unknown_items() -> None:
    logistics = LogisticsReport(
        fetched_at_iso="2026-08-01T00:00:00+00:00",
        source_base_url="http://eco.example",
        market_summaries=[
            {
                "item": "CookedCornItem",
                "supplyQty": 0,
                "demandQty": 25,
                "sellerCount": 0,
                "buyerCount": 1,
                "sources": ["live"],
            }
        ],
        supply_gaps=[{"item": "CookedCornItem", "demandQty": 25, "supplyQty": 0}],
    )
    report = build_food_report(_recipes(), _items(), logistics)

    assert [(row["item"], row["signal"]) for row in report.signals] == [
        ("CookedCornItem", "restock")
    ]


def test_food_report_marks_live_stock_without_demand_as_potential_overstock() -> None:
    logistics = LogisticsReport(
        fetched_at_iso="2026-08-01T00:00:00+00:00",
        source_base_url="http://eco.example",
        market_summaries=[
            {
                "item": "CookedCornItem",
                "supplyQty": 40,
                "demandQty": 0,
                "sellerCount": 1,
                "buyerCount": 0,
                "sources": ["live"],
            }
        ],
    )
    report = build_food_report(_recipes(), _items(), logistics)

    assert report.signals[0]["signal"] == "potential_overstock"


def test_food_report_keeps_history_only_data_insufficient() -> None:
    logistics = LogisticsReport(
        fetched_at_iso="2026-08-01T00:00:00+00:00",
        source_base_url="http://eco.example",
        market_summaries=[
            {
                "item": "CookedCornItem",
                "supplyQty": 40,
                "demandQty": 0,
                "sellerCount": 1,
                "buyerCount": 0,
                "sources": ["history"],
            }
        ],
    )
    report = build_food_report(_recipes(), _items(), logistics)

    assert report.signals[0]["signal"] == "insufficient"


def test_preview_food_json_route(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_food_report(**_kwargs: object) -> FoodReport:
        return build_food_report(_recipes(), _items(), LogisticsReport("now", "http://eco.example"))

    monkeypatch.setattr("eco_mcp_app.http_app.fetch_food_report", fake_fetch_food_report)
    response = TestClient(create_app()).get("/preview/food.json")

    assert response.status_code == 200
    assert response.json()["view"] == "food_signals"
