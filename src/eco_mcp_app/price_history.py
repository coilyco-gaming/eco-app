"""Current-cycle item price distribution plus production-capability markers.

This is the interpretation layer for eco-app#198 and eco-app#199. It keeps the
existing trade ledger, recipe graph, and progression exporters as the owning
sources, then joins them for one selected item and currency. Historical cycles
are deliberately excluded because their star and progression rules may differ.
"""

from __future__ import annotations

import asyncio
import math
import statistics
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import httpx

from .crafting import prettify_eco_name
from .market import ItemMarket, build_market
from .progression import ProgressionHistory, fetch_history
from .recipes import Recipe, RecipeIndex, load_recipe_index
from .trades import TradesLedger, fetch_ledger

THIN_SAMPLE_COUNT = 5
STALE_AFTER_DAYS = 3
MAX_HISTOGRAM_BUCKETS = 10
PROGRESSION_RULES_VERSION = "current-cycle-v1"


def _normalize_item(value: str) -> str:
    normalized = "".join(ch for ch in (value or "").lower() if ch.isalnum())
    return normalized[:-4] if normalized.endswith("item") else normalized


def _normalize_skill(value: str) -> str:
    normalized = "".join(ch for ch in (value or "").lower() if ch.isalnum())
    return normalized[:-5] if normalized.endswith("skill") else normalized


def _number(row: dict[str, Any], key: str) -> float | None:
    raw = row.get(key)
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _quantile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * fraction
    lower = math.floor(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * weight


def _histogram(values: list[float]) -> list[dict[str, Any]]:
    if not values:
        return []
    low = min(values)
    high = max(values)
    if low == high:
        return [{"low": low, "high": high, "count": len(values)}]

    bucket_count = min(MAX_HISTOGRAM_BUCKETS, max(3, math.ceil(math.sqrt(len(values)))))
    width = (high - low) / bucket_count
    counts = [0] * bucket_count
    for value in values:
        index = min(int((value - low) / width), bucket_count - 1)
        counts[index] += 1
    return [
        {
            "low": low + index * width,
            "high": high if index == bucket_count - 1 else low + (index + 1) * width,
            "count": count,
        }
        for index, count in enumerate(counts)
    ]


def _is_multimodal(histogram: list[dict[str, Any]], sample_count: int) -> bool:
    """Detect two material occupied groups separated by at least one empty bin.

    A lone outlier does not become a second mode. Each occupied group must carry
    at least 20% of samples, with an absolute floor of two observations.
    """
    material_floor = max(2, math.ceil(sample_count * 0.2))
    groups: list[int] = []
    current = 0
    for bucket in histogram:
        count = int(bucket["count"])
        if count:
            current += count
        elif current:
            groups.append(current)
            current = 0
    if current:
        groups.append(current)
    return sum(group >= material_floor for group in groups) >= 2


def _distribution(
    values: list[float],
    *,
    latest_day: int | None,
    observed_through_day: int | None,
) -> dict[str, Any]:
    sorted_values = sorted(values)
    histogram = _histogram(sorted_values)
    sample_count = len(sorted_values)
    sample_state = (
        "no_data"
        if sample_count == 0
        else "thin"
        if sample_count < THIN_SAMPLE_COUNT
        else "representative"
    )
    freshness_state = "unknown"
    if latest_day is not None and observed_through_day is not None:
        freshness_state = (
            "stale" if observed_through_day - latest_day >= STALE_AFTER_DAYS else "current"
        )
    shape_state = (
        "unknown"
        if sample_count < THIN_SAMPLE_COUNT
        else "multimodal"
        if _is_multimodal(histogram, sample_count)
        else "observed"
    )
    return {
        "sampleCount": sample_count,
        "sampleState": sample_state,
        "freshnessState": freshness_state,
        "shapeState": shape_state,
        "median": statistics.median(sorted_values) if sorted_values else None,
        "min": sorted_values[0] if sorted_values else None,
        "max": sorted_values[-1] if sorted_values else None,
        "percentiles": (
            {
                "p10": _quantile(sorted_values, 0.10),
                "p25": _quantile(sorted_values, 0.25),
                "p50": _quantile(sorted_values, 0.50),
                "p75": _quantile(sorted_values, 0.75),
                "p90": _quantile(sorted_values, 0.90),
            }
            if sorted_values
            else None
        ),
        "histogram": histogram,
    }


def _recipe_variants(item: str, recipes: RecipeIndex) -> list[Recipe]:
    wanted = _normalize_item(item)
    names: set[str] = set()
    for product, recipe_names in recipes.by_product.items():
        if _normalize_item(product) == wanted:
            names.update(recipe_names)

    by_name = {recipe.name: recipe for recipe in recipes.recipes}
    queue = list(names)
    while queue:
        recipe = by_name.get(queue.pop())
        if recipe is None:
            continue
        for variant in recipe.variants:
            if variant not in names:
                names.add(variant)
                queue.append(variant)
    return sorted(
        (by_name[name] for name in names if name in by_name),
        key=lambda recipe: (recipe.display_name, recipe.name),
    )


def _specialty_markers(
    variants: list[Recipe],
    recipes: RecipeIndex,
    progression: ProgressionHistory | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    skills = {skill["name"]: skill for skill in recipes.skills}
    required_by: dict[str, list[str]] = defaultdict(list)
    for recipe in variants:
        if recipe.skill_name:
            required_by[recipe.skill_name].append(recipe.name)

    progression_available = bool(
        progression is not None and "GainSpecialty" in progression.per_action_counts
    )
    first_gains = {
        _normalize_skill(gain.get("skill", "")): gain
        for gain in (progression.first_specialty_gains if progression else [])
        if gain.get("skill")
    }
    states: list[str] = []
    if required_by and not progression_available:
        states.append("missing_progression")

    markers: list[dict[str, Any]] = []
    for skill_name, recipe_names in sorted(required_by.items()):
        definition = skills.get(skill_name) or {}
        gain = first_gains.get(_normalize_skill(skill_name)) if progression_available else None
        status = (
            "progression_unavailable"
            if not progression_available
            else "observed"
            if gain
            else "unobserved"
        )
        markers.append(
            {
                "skill": skill_name,
                "skillPretty": definition.get("displayName") or prettify_eco_name(skill_name),
                "day": gain.get("day") if gain else None,
                "time": gain.get("time") if gain else None,
                "status": status,
                "recipeVariants": sorted(recipe_names),
            }
        )
    markers.sort(
        key=lambda marker: (
            marker["day"] is None,
            marker["day"] if marker["day"] is not None else math.inf,
            marker["skillPretty"],
        )
    )
    if any(marker["status"] == "unobserved" for marker in markers):
        states.append("unobserved_unlocks")
    return markers, states


def build_item_price_history(
    item: str,
    currency: str,
    rows: Iterable[dict[str, Any]],
    recipes: RecipeIndex,
    progression: ProgressionHistory | None,
    *,
    fetched_at_iso: str | None = None,
    warnings: Iterable[str] = (),
) -> dict[str, Any]:
    """Build one current-cycle price-history interpretation contract."""
    all_rows = list(rows)
    wanted_item = _normalize_item(item)
    wanted_currency = currency.strip().lower()

    observed_days = [
        int(day) for row in all_rows if (day := _number(row, "day")) is not None and day >= 0
    ]
    if progression is not None:
        observed_days.extend(
            int(gain["day"])
            for gain in progression.first_specialty_gains
            if gain.get("day") is not None
        )
    observed_through_day = max(observed_days, default=None)

    matching_rows = [
        row
        for row in all_rows
        if _normalize_item(str(row.get("item") or "")) == wanted_item
        and str(row.get("currency") or "").strip().lower() == wanted_currency
        and (_number(row, "unitPrice") or 0) > 0
    ]
    values = [value for row in matching_rows if (value := _number(row, "unitPrice")) is not None]
    selected_days = [
        int(day) for row in matching_rows if (day := _number(row, "day")) is not None and day >= 0
    ]
    markets = build_market(matching_rows, top_markets=0)
    market: ItemMarket | None = markets[0] if markets else None
    latest_day = market.latest_day if market else None

    variants = _recipe_variants(item, recipes)
    markers, states = _specialty_markers(variants, recipes, progression)
    distribution = _distribution(
        values,
        latest_day=latest_day,
        observed_through_day=observed_through_day,
    )
    for degraded in ("no_data", "thin"):
        if distribution["sampleState"] == degraded:
            states.append(degraded)
    if distribution["freshnessState"] == "stale":
        states.append("stale")
    if distribution["shapeState"] == "multimodal":
        states.append("multimodal")
    if not variants:
        states.append("missing_recipes")

    recipe_rows = [
        {
            "name": recipe.name,
            "displayName": recipe.display_name,
            "product": recipe.product.item,
            "skill": recipe.skill_name,
            "skillPretty": (
                next(
                    (
                        skill["displayName"]
                        for skill in recipes.skills
                        if skill["name"] == recipe.skill_name
                    ),
                    prettify_eco_name(recipe.skill_name or ""),
                )
                if recipe.skill_name
                else None
            ),
            "skillLevel": recipe.skill_level,
        }
        for recipe in variants
    ]

    return {
        "view": "item-price-history",
        "fetchedAtISO": fetched_at_iso or datetime.now(UTC).isoformat(),
        "item": item,
        "itemPretty": prettify_eco_name(item),
        "currency": currency,
        "scope": {
            "label": "Current cycle only",
            "cycle": "current",
            "progressionRulesVersion": PROGRESSION_RULES_VERSION,
            "historicalCyclesIncluded": False,
        },
        "window": {
            "label": "Current cycle",
            "firstObservedDay": min(selected_days, default=None),
            "latestPriceDay": latest_day,
            "observedThroughDay": observed_through_day,
        },
        "distribution": distribution,
        "daily": [bucket.to_dict() for bucket in market.buckets] if market else [],
        "totalVolume": market.total_volume if market else 0.0,
        "recipes": recipe_rows,
        "specialtyUnlocks": markers,
        "states": sorted(set(states)),
        "warnings": list(dict.fromkeys(warnings)),
    }


async def fetch_item_price_history(
    item: str,
    currency: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Fetch the existing sources concurrently and degrade each one explicitly."""
    ledger_result, progression_result = await asyncio.gather(
        fetch_ledger(base_url=base_url, api_key=api_key, client=client),
        fetch_history(base_url=base_url, api_key=api_key, client=client),
        return_exceptions=True,
    )
    warnings: list[str] = []
    if isinstance(ledger_result, BaseException):
        ledger = TradesLedger(
            fetched_at_iso=datetime.now(UTC).isoformat(),
            source_base_url=base_url or "",
        )
        warnings.append(f"market history unavailable: {type(ledger_result).__name__}")
    else:
        ledger = ledger_result
        warnings.extend(ledger.warnings)

    progression: ProgressionHistory | None
    if isinstance(progression_result, BaseException):
        progression = None
        warnings.append(f"progression unavailable: {type(progression_result).__name__}")
    else:
        progression = progression_result
        warnings.extend(progression.warnings)

    return build_item_price_history(
        item,
        currency,
        ledger.trades,
        load_recipe_index(),
        progression,
        fetched_at_iso=ledger.fetched_at_iso,
        warnings=warnings,
    )
