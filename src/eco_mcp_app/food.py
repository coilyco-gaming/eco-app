"""Food restock signals built from read-only recipe, shelf, trade, and crafting data."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from .crafting import prettify_eco_name
from .items import ItemIndex, fetch_item_index
from .logistics import LogisticsReport, fetch_logistics
from .recipes import RecipeIndex, load_recipe_index

_FOOD_SKILL_TOKENS = ("chef", "cook", "baking")


def food_product_ids(recipes: RecipeIndex) -> set[str]:
    """Return only recipe products positively identified by a food profession."""
    food: set[str] = set()
    for recipe in recipes.recipes:
        skill = (recipe.skill_name or "").lower()
        if any(token in skill for token in _FOOD_SKILL_TOKENS):
            food.add(recipe.product.item)
    return food


@dataclass
class FoodReport:
    fetched_at_iso: str
    source_base_url: str
    signals: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "view": "food_signals",
            "fetchedAtISO": self.fetched_at_iso,
            "sourceBaseUrl": self.source_base_url,
            "foodCount": len(self.signals),
            "signals": list(self.signals),
            "warnings": list(self.warnings),
        }


def build_food_report(
    recipes: RecipeIndex,
    items: ItemIndex,
    logistics: LogisticsReport,
) -> FoodReport:
    """Classify confirmed food products without inferring shelf freshness."""
    food_ids = food_product_ids(recipes)
    item_stats = {row["item"]: row for row in items.items}
    markets: dict[str, list[dict[str, Any]]] = {}
    for market in logistics.market_summaries:
        markets.setdefault(market["item"], []).append(market)
    gaps = {row["item"]: row for row in logistics.supply_gaps}

    rows: list[dict[str, Any]] = []
    for item in sorted(food_ids, key=prettify_eco_name):
        stat = item_stats.get(item, {})
        market_rows = markets.get(item, [])
        supply_qty = sum(float(row["supplyQty"]) for row in market_rows)
        demand_qty = sum(float(row["demandQty"]) for row in market_rows)
        live = bool(market_rows) and all("live" in row["sources"] for row in market_rows)
        trade_count = int(stat.get("tradeCount", 0))
        craft_count = float(stat.get("craftCount", 0))
        gap = gaps.get(item)

        signal = "insufficient"
        reason = "No live shelf observation is available for this confirmed food item."
        if live and gap is not None:
            signal = "restock"
            reason = (
                f"Live shelves show {gap['demandQty']:,.0f} units wanted with "
                f"{gap['supplyQty']:,.0f} supplied."
            )
        elif live and supply_qty > 0 and demand_qty == 0 and craft_count > 0:
            signal = "potential_overstock"
            reason = (
                f"Live shelves show {supply_qty:,.0f} units for sale with no purchase order "
                "observed."
            )
        elif live and supply_qty > 0 and demand_qty > 0:
            signal = "balanced"
            reason = f"Live shelves show {supply_qty:,.0f} supplied and {demand_qty:,.0f} wanted."
        elif live:
            reason = "Live shelves do not provide enough matching supply and demand evidence."

        rows.append(
            {
                "item": item,
                "itemPretty": prettify_eco_name(item),
                "signal": signal,
                "reason": reason,
                "live": live,
                "supplyQty": round(supply_qty, 2),
                "demandQty": round(demand_qty, 2),
                "tradeCount": trade_count,
                "craftCount": round(craft_count, 2),
            }
        )

    rank = {"restock": 0, "potential_overstock": 1, "balanced": 2, "insufficient": 3}
    rows.sort(key=lambda row: (rank[row["signal"]], -(row["demandQty"] + row["supplyQty"])))
    return FoodReport(
        fetched_at_iso=logistics.fetched_at_iso,
        source_base_url=logistics.source_base_url,
        signals=rows,
        warnings=[*recipes.warnings, *items.warnings, *logistics.warnings],
    )


async def fetch_food_report(
    base_url: str | None = None,
    api_key: str | None = None,
) -> FoodReport:
    recipes = load_recipe_index()
    items, logistics = await asyncio.gather(
        fetch_item_index(base_url=base_url, api_key=api_key),
        fetch_logistics(base_url=base_url, api_key=api_key),
    )
    return build_food_report(recipes, items, logistics)


__all__ = ["FoodReport", "build_food_report", "fetch_food_report", "food_product_ids"]
