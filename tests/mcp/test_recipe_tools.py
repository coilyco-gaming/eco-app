"""The recipe / cost plane finally has an MCP surface (eco-app#242).

Eco Gnome was the one substantial dataset in eco-app answering only a browser.
An agent asking "what does a Steel Axe cost to make, and is that above or below
market?" could not get there, even though the app computes exactly that for the
SPA.

Response size is designed in rather than retrofitted — the graph is ~1,450
recipes, which is the eco-app#240 family-3 trap.
"""

from __future__ import annotations

import json
from typing import Any

import mcp.types as mt
import pytest
from starlette.testclient import TestClient

from eco_mcp_app.http_app import create_app
from eco_mcp_app.recipes import load_recipe_index
from eco_mcp_app.wave3_routes import DEFAULT_RECIPE_LIMIT, skills_payload


async def _call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from eco_mcp_app.server import build_server

    mcp = build_server()
    handler = mcp.request_handlers[mt.CallToolRequest]
    result = await handler(
        mt.CallToolRequest(
            method="tools/call",
            params=mt.CallToolRequestParams(name=name, arguments=arguments),
        )
    )
    for block in result.root.content:
        try:
            parsed = json.loads(getattr(block, "text", "") or "")
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise AssertionError(f"{name} returned no JSON block")


@pytest.mark.asyncio
async def test_get_recipes_is_summary_first() -> None:
    """Unfiltered, the graph is far past an MCP response cap."""
    payload = await _call("get_recipes", {})
    assert payload["recipesReturned"] <= DEFAULT_RECIPE_LIMIT
    assert payload["recipesMatched"] > DEFAULT_RECIPE_LIMIT
    # The truncation announces itself rather than looking like the whole graph.
    assert any("showing" in w for w in payload["warnings"])


@pytest.mark.asyncio
async def test_a_filter_narrows_to_a_real_answer() -> None:
    index = load_recipe_index()
    skill = next(r.skill_name for r in index.recipes if r.skill_name)
    payload = await _call("get_recipes", {"skill": skill, "limit": 5})
    assert payload["recipesReturned"] <= 5
    assert payload["recipesMatched"] >= 1


@pytest.mark.asyncio
async def test_limit_zero_returns_everything() -> None:
    """The SPA's contract: it renders the whole graph."""
    payload = await _call("get_recipes", {"limit": 0})
    assert payload["recipesReturned"] == payload["recipesMatched"]


@pytest.mark.asyncio
async def test_the_payload_names_its_provenance() -> None:
    """A consumer must be able to tell vanilla-seed from a modded export (#179)."""
    payload = await _call("get_recipes", {"limit": 1})
    assert payload["source"]
    assert payload["sourceKind"]
    assert "serverSpecific" in payload


@pytest.mark.asyncio
async def test_price_recipe_costs_a_product() -> None:
    index = load_recipe_index()
    product = index.recipes[0].product.item
    payload = await _call("price_recipe", {"product": product})
    rows = payload["recipes"]
    assert rows, "no recipe matched a product taken from the index itself"
    # The cost engine ran: every row carries a breakdown, priced or not.
    assert all("cost" in row for row in rows)


@pytest.mark.asyncio
async def test_get_skills_reports_recipe_coverage() -> None:
    payload = await _call("get_skills", {})
    assert payload["skills"]
    assert payload["counts"]["skills"] == len(payload["skills"])
    # Ranked by coverage, so the profession axis reads at a glance.
    counts = [s["recipeCount"] for s in payload["skills"]]
    assert counts == sorted(counts, reverse=True)


def test_skills_payload_counts_each_skills_recipes() -> None:
    index = load_recipe_index()
    payload = skills_payload(index)
    total = sum(s["recipeCount"] for s in payload["skills"])
    assert total == payload["counts"]["recipesCovered"]
    assert total > 0


def test_the_spa_recipe_route_keeps_its_contract() -> None:
    """`/preview/recipes.json` moved onto the registry but kept its params."""
    client = TestClient(create_app())
    r = client.get("/preview/recipes.json", params={"limit": 0})
    assert r.status_code == 200
    payload = r.json()
    # The shape the recipes page reads.
    for key in ("recipes", "byProduct", "bySkill", "byStation", "skills", "tags", "source"):
        assert key in payload, key

    # And the filters still filter.
    filtered = client.get(
        "/preview/recipes.json", params={"skill": "__no_such_skill__", "limit": 0}
    )
    assert filtered.status_code == 200
    assert filtered.json()["recipes"] == []
