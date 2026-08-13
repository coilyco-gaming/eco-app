"""Inlined images are opt-in so a lookup fits an MCP response (eco-app#230).

`get_species(name="Snapping Turtle")` returned 286,264 characters, of which
285,619 were one base64 JPEG wrapped around a 150-character wiki extract and a
52-character taxonomy. The response exceeded the client's token cap, so the
caller got an error and a spill-file path instead of two sentences.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from eco_mcp_app import species as species_mod
from eco_mcp_app import wikidata as wikidata_mod
from eco_mcp_app.wave2_routes import ExplainItemInput, SpeciesInput

_PHOTO_URL = "https://inaturalist-open-data.s3.amazonaws.com/photos/1/medium.jpg"
# Stands in for the 285 KB JPEG.
_PHOTO_BYTES = b"\xff\xd8\xff" + b"\x00" * 200_000

_TAXON: dict[str, Any] = {
    "id": 1,
    "name": "Chelydra serpentina",
    "preferred_common_name": "Snapping Turtle",
    "default_photo": {"medium_url": _PHOTO_URL, "attribution": "(c) someone, CC-BY"},
    "wikipedia_summary": "A large freshwater turtle. It has a powerful beak-like jaw.",
    "ancestors": [],
}


@pytest.fixture(autouse=True)
def _no_population(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _empty(species_id: str) -> list[species_mod.PopulationSample]:
        return []

    monkeypatch.setattr(species_mod, "fetch_species_population", _empty)

    async def _taxon(name: str) -> dict[str, Any]:
        return _TAXON

    monkeypatch.setattr(species_mod, "_fetch_inat_taxon", _taxon)

    async def _photo(url: str) -> bytes:
        return _PHOTO_BYTES

    monkeypatch.setattr(species_mod, "_fetch_inat_photo_bytes", _photo)


@pytest.fixture(autouse=True)
def _tmp_wikidata_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    db = tmp_path / "wikidata.sqlite"
    monkeypatch.setenv("ECO_MCP_WIKIDATA_CACHE", str(db))
    yield db


def test_the_tool_schemas_default_to_no_inlined_image() -> None:
    # The contract an MCP caller sees. The builders still default to inlining
    # because the web surfaces want the bytes; the tools opt out.
    assert SpeciesInput(name="Bison").include_image is False
    assert ExplainItemInput(name="Iron").include_image is False


@pytest.mark.asyncio
async def test_species_omits_the_image_when_not_requested() -> None:
    payload = (
        await species_mod.build_species_payload("SnappingTurtleSpecies", include_image=False)
    ).to_dict()
    assert payload["photoDataUri"] is None
    # The URL survives, so a caller that wants the image can still get it.
    assert payload["photoUrl"] == _PHOTO_URL
    assert payload["photoAttribution"] == "(c) someone, CC-BY"
    # The point of the fix: the answer now fits in a response.
    assert len(json.dumps(payload)) < 5_000


@pytest.mark.asyncio
async def test_species_inlines_the_image_on_request() -> None:
    payload = (
        await species_mod.build_species_payload("SnappingTurtleSpecies", include_image=True)
    ).to_dict()
    assert payload["photoDataUri"] is not None
    assert payload["photoDataUri"].startswith("data:image/jpeg;base64,")
    assert payload["photoUrl"] == _PHOTO_URL
    assert len(json.dumps(payload)) > 100_000


@respx.mock
@pytest.mark.asyncio
async def test_explain_item_omits_the_image_when_not_requested() -> None:
    respx.get("https://en.wikipedia.org/api/rest_v1/page/summary/Wheat").mock(
        return_value=httpx.Response(
            200,
            json={
                "title": "Wheat",
                "extract": "Wheat is a group of wild and domesticated grasses.",
                "thumbnail": {"source": "https://upload.wikimedia.org/wheat.jpg"},
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Wheat"}},
                "type": "standard",
            },
        )
    )
    card = await wikidata_mod.build_ecopedia_card("Wheat", include_image=False)
    assert card.image_data_uri is None
    assert card.image_url == "https://upload.wikimedia.org/wheat.jpg"
    assert len(json.dumps(card.to_dict())) < 5_000
