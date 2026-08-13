"""Tests for `wikidata.build_ecopedia_card` and the `explain_item` tool.

Mirrors the respx-driven patterns used in `test_fetch_eco_info.py` +
`test_smoke.py`. The SQLite cache is pointed at a per-test temp file so the
real `~/.cache/eco-mcp-app/wikidata.sqlite` is never touched.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import mcp.types as mt
import pytest
import respx

from eco_mcp_app.server import build_server
from eco_mcp_app.wikidata import (
    WIKIDATA_SPARQL_URL,
    build_ecopedia_card,
    cache_path,
)


@pytest.fixture(autouse=True)
def _tmp_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    db = tmp_path / "wikidata.sqlite"
    monkeypatch.setenv("ECO_MCP_WIKIDATA_CACHE", str(db))
    yield db


_IRON_SPARQL = {
    "head": {"vars": ["item", "itemLabel", "itemDescription", "image", "Atomic_number"]},
    "results": {
        "bindings": [
            {
                "item": {
                    "type": "uri",
                    "value": "http://www.wikidata.org/entity/Q677",
                },
                "itemLabel": {"type": "literal", "value": "iron"},
                "itemDescription": {
                    "type": "literal",
                    "value": "chemical element with atomic number 26",
                },
                "image": {
                    "type": "uri",
                    "value": "https://upload.wikimedia.org/iron.jpg",
                },
                "Atomic_number": {"type": "literal", "value": "26"},
            }
        ]
    },
}

_WIKIPEDIA_OAK = {
    "title": "Oak",
    "extract": "An oak is a tree or shrub in the genus Quercus.",
    "thumbnail": {"source": "https://upload.wikimedia.org/oak.jpg"},
    "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Oak"}},
    "type": "standard",
}


def _mock_image(url: str) -> None:
    respx.get(url).mock(
        return_value=httpx.Response(
            200, content=b"\xff\xd8\xffFAKEJPG", headers={"content-type": "image/jpeg"}
        )
    )


@respx.mock
@pytest.mark.asyncio
async def test_build_card_iron_via_sparql() -> None:
    respx.get(WIKIDATA_SPARQL_URL).mock(return_value=httpx.Response(200, json=_IRON_SPARQL))
    _mock_image("https://upload.wikimedia.org/iron.jpg")
    # Wikipedia extract supplements the Wikidata description.
    respx.get("https://en.wikipedia.org/api/rest_v1/page/summary/Iron").mock(
        return_value=httpx.Response(
            200,
            json={
                "title": "Iron",
                "extract": "Iron is a chemical element; it has symbol Fe.",
                "type": "standard",
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Iron"}},
            },
        )
    )

    card = await build_ecopedia_card("Iron", category="material")
    assert card.title.lower() == "iron"
    assert "chemical element" in card.description.lower()
    assert ("Atomic number", "26") in card.facts
    assert card.image_data_uri is not None
    assert card.image_data_uri.startswith("data:image/jpeg;base64,")
    assert card.source == "Wikidata"


@respx.mock
@pytest.mark.asyncio
async def test_build_card_oak_via_wikipedia_fallback() -> None:
    # No category -> hit Wikipedia first.
    respx.get("https://en.wikipedia.org/api/rest_v1/page/summary/Oak").mock(
        return_value=httpx.Response(200, json=_WIKIPEDIA_OAK)
    )
    _mock_image("https://upload.wikimedia.org/oak.jpg")

    card = await build_ecopedia_card("Oak")
    assert card.title == "Oak"
    assert "oak" in card.description.lower()
    assert card.source == "Wikipedia"
    assert card.image_data_uri is not None
    assert card.source_url == "https://en.wikipedia.org/wiki/Oak"


@respx.mock
@pytest.mark.asyncio
async def test_build_card_wikipedia_404_returns_not_found() -> None:
    respx.get("https://en.wikipedia.org/api/rest_v1/page/summary/Nonexistentium").mock(
        return_value=httpx.Response(404, json={"type": "not_found"})
    )
    # Also mock SPARQL fallback attempts to return empty across all categories.
    respx.get(WIKIDATA_SPARQL_URL).mock(
        return_value=httpx.Response(200, json={"results": {"bindings": []}})
    )

    card = await build_ecopedia_card("Nonexistentium")
    assert card.not_found is True
    assert card.title == "Nonexistentium"


@respx.mock
@pytest.mark.asyncio
async def test_unsupported_category_returns_helpful_error() -> None:
    card = await build_ecopedia_card("Iron", category="artifact")
    assert card.not_found is True
    assert "Unsupported category" in card.description


@respx.mock
@pytest.mark.asyncio
async def test_sparql_result_is_cached_on_repeat() -> None:
    route = respx.get(WIKIDATA_SPARQL_URL).mock(return_value=httpx.Response(200, json=_IRON_SPARQL))
    _mock_image("https://upload.wikimedia.org/iron.jpg")
    respx.get("https://en.wikipedia.org/api/rest_v1/page/summary/Iron").mock(
        return_value=httpx.Response(404, json={})
    )

    await build_ecopedia_card("Iron", category="material")
    await build_ecopedia_card("Iron", category="material")
    # Second call reads both SPARQL + image from the SQLite cache.
    assert route.call_count == 1
    # Cache file was created.
    assert cache_path().exists()


@respx.mock
@pytest.mark.asyncio
async def test_explain_item_tool_wraps_card() -> None:
    respx.get(WIKIDATA_SPARQL_URL).mock(return_value=httpx.Response(200, json=_IRON_SPARQL))
    _mock_image("https://upload.wikimedia.org/iron.jpg")
    respx.get("https://en.wikipedia.org/api/rest_v1/page/summary/Iron").mock(
        return_value=httpx.Response(404, json={})
    )

    mcp = build_server()
    handler = mcp.request_handlers[mt.CallToolRequest]
    req = mt.CallToolRequest(
        method="tools/call",
        params=mt.CallToolRequestParams(
            name="explain_item",
            arguments={"name": "Iron", "category": "material"},
        ),
    )
    result = await handler(req)
    blocks = result.root.content
    assert len(blocks) == 2
    assert isinstance(blocks[0], mt.TextContent)
    assert isinstance(blocks[1], mt.TextContent)
    md = blocks[0].text
    payload = json.loads(blocks[1].text)
    assert "iron" in md.lower()
    assert payload["title"].lower() == "iron"
    # Just-data per eco-app#87: explain_item no longer emits a widget.
    assert result.root.meta is None


@pytest.mark.asyncio
async def test_explain_item_requires_name() -> None:
    mcp = build_server()
    handler = mcp.request_handlers[mt.CallToolRequest]
    req = mt.CallToolRequest(
        method="tools/call",
        params=mt.CallToolRequestParams(name="explain_item", arguments={"name": "   "}),
    )
    result = await handler(req)
    assert result.root.isError is True


# ---------------------------------------------------------------------------
# The category parameter is applied and echoed (eco-app#233)
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_category_is_echoed_when_wikipedia_answers() -> None:
    """`explain_item(name="Wheat", category="plant")` echoed `category: null`.

    The Wikipedia branch hardcoded `category=None`, so whenever SPARQL missed
    the caller's hint vanished from the response and the parameter looked
    inert (eco-app#233).
    """
    respx.get(WIKIDATA_SPARQL_URL).mock(
        return_value=httpx.Response(200, json={"results": {"bindings": []}})
    )
    respx.get("https://en.wikipedia.org/api/rest_v1/page/summary/Wheat").mock(
        return_value=httpx.Response(
            200,
            json={
                "title": "Wheat",
                "extract": "Wheat is a group of wild and domesticated grasses.",
                "type": "standard",
            },
        )
    )
    card = await build_ecopedia_card("Wheat", "plant", include_image=False)
    assert card.category == "plant"
    payload = card.to_dict()
    assert payload["category"] == "plant"


@respx.mock
@pytest.mark.asyncio
async def test_empty_facts_explain_themselves() -> None:
    """A bare `facts: []` against a documented promise read as broken."""
    respx.get(WIKIDATA_SPARQL_URL).mock(
        return_value=httpx.Response(200, json={"results": {"bindings": []}})
    )
    respx.get("https://en.wikipedia.org/api/rest_v1/page/summary/Wheat").mock(
        return_value=httpx.Response(
            200, json={"title": "Wheat", "extract": "A grass.", "type": "standard"}
        )
    )
    card = await build_ecopedia_card("Wheat", "plant", include_image=False)
    assert card.facts == []
    assert card.facts_note is not None
    # Names the category, the item, and what was looked for.
    assert "plant" in card.facts_note
    assert "Wheat" in card.facts_note
    assert "Taxon rank" in card.facts_note


@respx.mock
@pytest.mark.asyncio
async def test_no_category_says_to_pass_one() -> None:
    respx.get("https://en.wikipedia.org/api/rest_v1/page/summary/Wheat").mock(
        return_value=httpx.Response(
            200, json={"title": "Wheat", "extract": "A grass.", "type": "standard"}
        )
    )
    card = await build_ecopedia_card("Wheat", include_image=False)
    assert card.category is None
    assert card.facts_note is not None
    assert "No category was supplied" in card.facts_note


@respx.mock
@pytest.mark.asyncio
async def test_a_returned_image_carries_a_credit() -> None:
    """image_credit was null while an image was returned (eco-app#233)."""
    respx.get("https://en.wikipedia.org/api/rest_v1/page/summary/Wheat").mock(
        return_value=httpx.Response(
            200,
            json={
                "title": "Wheat",
                "extract": "A grass.",
                "type": "standard",
                "thumbnail": {"source": "https://upload.wikimedia.org/wheat.jpg"},
            },
        )
    )
    card = await build_ecopedia_card("Wheat", include_image=False)
    assert card.image_url == "https://upload.wikimedia.org/wheat.jpg"
    assert card.image_credit == "https://upload.wikimedia.org/wheat.jpg"
