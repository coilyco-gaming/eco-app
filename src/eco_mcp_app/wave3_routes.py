"""Typed dual registrations for the recipe / cost wave (eco-app#242).

Eco Gnome was the one substantial dataset in eco-app with no MCP surface: the
recipe graph and the cost engine answered only a browser, at
``/preview/recipes.json``. An agent asking "what does a Steel Axe cost to make
on Sirens, and is that above or below market?" could not get there, even though
the app computes exactly that for the SPA.

These three routes register through the same ``DualRouteRegistry`` the other
waves use, so one typed contract lands on REST and MCP together and
``/preview/recipes.json`` stops being a hand-written one-off.

Response size is designed in rather than retrofitted (the eco-app#240 family-3
lesson): the graph is ~1,450 recipes, so ``get_recipes`` is summary-first with
a ``limit`` from day one. The SPA asks for the whole graph explicitly.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .dual_routes import DualRouteRegistry
from .public_routes import ToolInvoker, register_json_route

# What an MCP client can absorb. The SPA passes limit=0 for the whole graph.
DEFAULT_RECIPE_LIMIT = 25


class RecipesInput(BaseModel):
    """Filter the recipe graph, and bound how much of it comes back."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    product: str | None = Field(
        default=None,
        description="Only recipes producing this item id, e.g. SteelAxeItem.",
    )
    skill: str | None = Field(
        default=None, description="Only recipes requiring this skill, e.g. Smelting."
    )
    station: str | None = Field(
        default=None,
        description="Only recipes crafted at this station, e.g. AnvilItem.",
    )
    # The SPA's existing query params. `/preview/recipes.json` kept its path
    # when the bespoke handler was replaced, so it keeps its contract too
    # (eco-app#242) — the recipes and cost pages pass these today.
    cost: str | None = Field(
        default=None,
        description="Truthy (1/true/yes/on) to run the cost engine over the returned recipes.",
    )
    server: str | None = Field(
        default=None,
        description="Eco server whose market prices the leaves when `cost` is on.",
    )
    # Aliased rather than renamed: the SPA already sends these spellings, and
    # `/preview/recipes.json` keeps its query params (eco-app#242).
    calorie_price: float = Field(
        default=0.0,
        alias="caloriePrice",
        description="Currency per calorie, to monetize the labor axis.",
    )
    minute_price: float = Field(
        default=0.0,
        alias="minutePrice",
        description="Currency per minute, to monetize the time axis.",
    )
    limit: int = Field(
        default=DEFAULT_RECIPE_LIMIT,
        ge=0,
        description=(
            "Maximum recipes to return. The full graph is ~1,450 recipes and will exceed an "
            "MCP client's response cap, so this defaults to a slice. 0 means no limit — the "
            "SPA uses that; an MCP caller should filter instead."
        ),
    )


class PriceRecipeInput(BaseModel):
    """Price a recipe against the live market."""

    model_config = ConfigDict(extra="forbid")

    product: str = Field(
        description="Item id to price the production of, e.g. SteelAxeItem.",
    )
    server: str | None = Field(
        default=None,
        description="Eco server whose market prices the leaves. Omit for the default.",
    )
    calorie_price: float = Field(
        default=0.0,
        description="Currency per calorie, to monetize the labor axis. 0 leaves it unpriced.",
    )
    minute_price: float = Field(
        default=0.0,
        description="Currency per minute, to monetize the time axis. 0 leaves it unpriced.",
    )


class SkillsInput(BaseModel):
    """No arguments: the whole skill axis is small."""

    model_config = ConfigDict(extra="forbid")


WAVE3_TOOL_NAMES = frozenset({"get_recipes", "price_recipe", "get_skills"})

WAVE3_PATHS: dict[str, str] = {
    # Keeps the SPA's established path and query params; the bespoke handler
    # this replaces lived here too.
    "get_recipes": "/preview/recipes.json",
    "price_recipe": "/preview/price_recipe.json",
    "get_skills": "/preview/get_skills.json",
}


def register_wave3_routes(registry: DualRouteRegistry, invoke: ToolInvoker) -> None:
    """Register the recipe / cost wave once."""
    present = {name for name in WAVE3_TOOL_NAMES if registry.has_tool(name)}
    if present:
        if present == WAVE3_TOOL_NAMES:
            return
        names = ", ".join(sorted(present))
        raise ValueError(f"Wave 3 routes partially overlap existing tools: {names}")

    register_json_route(
        registry,
        invoke,
        name="get_recipes",
        title="Eco - recipes and bills of materials",
        description=(
            "Look up Eco crafting recipes: ingredients, products, skill, station, and craft "
            "time. Filter by product, skill, or station. Summary-first — the full graph is "
            "~1,450 recipes, so pass a filter or raise `limit`. The payload names its source "
            "and whether it is the running server's modded graph or the vanilla seed."
        ),
        rest_path=WAVE3_PATHS["get_recipes"],
        input_model=RecipesInput,
    )
    register_json_route(
        registry,
        invoke,
        name="price_recipe",
        title="Eco - recipe cost and margin",
        description=(
            "Cost out an Eco recipe against the live market: per-unit ingredient cost, labor "
            "and time, the resulting margin, and which leaf prices came from the market "
            "versus went unpriced. An unreachable market degrades to all-unpriced rather "
            "than failing."
        ),
        rest_path=WAVE3_PATHS["price_recipe"],
        input_model=PriceRecipeInput,
    )
    register_json_route(
        registry,
        invoke,
        name="get_skills",
        title="Eco - skills and recipe coverage",
        description=(
            "List Eco's skills with how many recipes each one gates — the profession axis "
            "behind 'what is this specialty actually worth'."
        ),
        rest_path=WAVE3_PATHS["get_skills"],
        input_model=SkillsInput,
    )


def skills_payload(index: Any) -> dict[str, Any]:
    """Skills plus their recipe coverage, folded from a parsed index.

    Pure so it can be unit-tested without the tool wiring.
    """
    coverage: dict[str, int] = {}
    for recipe in index.recipes:
        name = recipe.skill_name
        if name:
            coverage[name] = coverage.get(name, 0) + 1
    skills = [
        {**skill, "recipeCount": coverage.get(str(skill.get("name", "")), 0)}
        for skill in index.skills
    ]
    skills.sort(key=lambda s: (-int(s["recipeCount"]), str(s.get("name", ""))))
    return {
        "view": "eco_skills",
        "fetchedAtISO": index.fetched_at_iso,
        "source": index.source,
        "sourceKind": index.source_kind,
        "serverSpecific": index.source_kind == "modded-export",
        "skills": skills,
        "counts": {"skills": len(skills), "recipesCovered": sum(coverage.values())},
        "warnings": list(index.warnings),
    }
