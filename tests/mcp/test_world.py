"""Tests for the world / industry activity aggregator + tool wiring (eco-app#62).

Covers:
  - Folding a world-action CSV into categories / builders / objects / timeline /
    hotspots via the shared crafting plumbing.
  - The eco-app#5 column corrector realigning a shifted world row.
  - Day-3 empty CSVs producing a graceful "no events" report.
  - The per-action max-rows safety valve.
  - fetch_world merging multiple actions with the id→name citizen join.
  - Partial-failure tolerance (a disabled/erroring exporter is a warning).
  - Ids shown when the citizen join is unavailable.
  - SQLite cache per (base, api-key) hitting within TTL.
  - to_dict / from_dict round-trip.
  - Tool wiring returns two TextContent blocks + _meta.ui, and list_tools sees it.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path

import httpx
import mcp.types as mt
import pytest
import respx

from eco_mcp_app.server import build_server
from eco_mcp_app.world import (
    WORLD_ACTIONS,
    WorldAccumulator,
    aggregate_world_rows,
    apply_citizen_names,
    fetch_world,
    finalize,
)

BASE = "http://eco.example.com:3001"
CITIZENS_URL = f"{BASE}/api/v1/citizens"


def _action_url(action: str) -> str:
    return f"{BASE}/api/v1/exporter/actions?actionName={action}"


_CITIZENS_JSON = [
    {"id": 129312, "name": "coilysiren"},
    {"id": 130409, "name": "ekans"},
    {"id": 129580, "name": "redwood"},
]

# Construction rows across two in-game days (Time in seconds; day = Time // 86400).
_CONSTRUCT_CSV = (
    "Block,Citizen,ActionLocation,Count,Time\n"
    '"StoneItem",129312,"418,75,460",12.0,6519\n'
    '"StoneItem",130409,"420,75,462",8.0,7000\n'
    '"BrickItem",129580,"100,80,120",5.0,95000\n'
)

# PlaceOrPickUpObject — a distinct object column.
_PLACE_CSV = (
    "WorldObjectItem,Citizen,ActionLocation,Count,Time\n"
    '"WorkbenchItem",129312,"418,75,460",1.0,6600\n'
    '"CampfireItem",129312,"418,75,460",1.0,6700\n'
)

_TAMP_CSV = 'Block,Citizen,ActionLocation,Count,Time\n"DirtRoadItem",130409,"300,70,300",4.0,8000\n'

_DIG_CSV = (
    "BlockItemOnDestroy,Citizen,Position,Count,Time\n"
    '"IronOreItem",129580,"500,40,500",30.0,9000\n'
    '"IronOreItem",129580,"501,40,500",22.0,9100\n'
)

_EMPTY_CSV = "Block,Citizen,ActionLocation,Count,Time\n"


@pytest.fixture(autouse=True)
def _isolated_cache(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Each test gets its own cache dir so SQLite state doesn't cross-leak."""
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("ECO_CACHE_DIR", tmp)
        yield Path(tmp)


def _rows(csv_text: str) -> list[list[str]]:
    import csv

    return list(csv.reader(csv_text.splitlines()))


def _mock_all_actions(overrides: dict[str, str] | None = None) -> None:
    """Mock every world-action endpoint empty, overriding named ones with CSVs."""
    overrides = overrides or {}
    seen: set[str] = set()
    for action, _cat in WORLD_ACTIONS:
        if action in seen:
            continue
        seen.add(action)
        text = overrides.get(action, _EMPTY_CSV)
        respx.get(_action_url(action)).mock(return_value=httpx.Response(200, text=text))


def test_aggregate_world_rows_folds_construction() -> None:
    acc = WorldAccumulator()
    n = aggregate_world_rows("ConstructOrDeconstruct", "construction", _rows(_CONSTRUCT_CSV), acc)
    assert n == 3
    assert acc.total_events == 3
    assert acc.category_events["construction"] == 3
    # Volume is the summed Count (12 + 8 + 5).
    assert acc.category_volume["construction"] == pytest.approx(25.0)
    # Objects count touch *events*, not summed Count: StoneItem is placed in
    # two rows → 2 touches (was 12 + 8 = 20 under the old volume bug, #82).
    assert acc.by_object["StoneItem"] == 2
    # Citizen keyed by raw numeric id; each row is one event.
    assert acc.by_citizen["129312"] == 1
    assert acc.by_citizen["130409"] == 1
    # Timeline buckets by in-game day: 6519/7000 → day 0, 95000 → day 1.
    assert acc.timeline[0]["construction"] == 2
    assert acc.timeline[1]["construction"] == 1
    # Hotspots bin x/z to the 64-grid: (418,_,460) → (384, 448).
    assert acc.hotspots[(384, 448)] == 2


def test_aggregate_world_rows_realigns_shifted_row() -> None:
    """An undeclared extra column shifts fields; the corrector recovers them."""
    acc = WorldAccumulator()
    csv_text = (
        "Block,Citizen,ActionLocation,Count,Time\n"
        # Aligned row.
        '"StoneItem",129312,"418,75,460",12.0,6519\n'
        # Shifted: an undeclared HandsItem column before ActionLocation.
        '"BrickItem",130409,"HandsItem","420,75,462",8.0,7000\n'
    )
    aggregate_world_rows("ConstructOrDeconstruct", "construction", _rows(csv_text), acc)
    # Both rows fold with real Count and Citizen despite the shift.
    assert acc.category_volume["construction"] == pytest.approx(20.0)
    assert acc.by_citizen["130409"] == 1
    # The position triple never becomes an object key.
    assert "420,75,462" not in acc.by_object


def test_aggregate_world_rows_empty_stays_empty() -> None:
    acc = WorldAccumulator()
    n = aggregate_world_rows("TampRoad", "roads", _rows(_EMPTY_CSV), acc)
    assert n == 0
    assert acc.total_events == 0
    assert dict(acc.category_events) == {}


def test_aggregate_world_rows_respects_max_rows_cap() -> None:
    acc = WorldAccumulator()
    n = aggregate_world_rows(
        "ConstructOrDeconstruct", "construction", _rows(_CONSTRUCT_CSV), acc, max_rows=2
    )
    assert n == 2
    assert any("truncated" in w for w in acc.warnings)


def test_finalize_ranks_and_round_trips() -> None:
    acc = WorldAccumulator()
    aggregate_world_rows("ConstructOrDeconstruct", "construction", _rows(_CONSTRUCT_CSV), acc)
    aggregate_world_rows("DigOrMine", "extraction", _rows(_DIG_CSV), acc)
    activity = finalize(acc, "t", BASE)
    # Categories ordered by CATEGORY_ORDER, only non-empty ones present.
    keys = activity.category_keys
    assert "construction" in keys and "extraction" in keys
    # Objects ranked by touch-event count (#82), not summed Count: StoneItem
    # (2 place rows) and IronOreItem (2 dig rows) each score 2 touches and lead
    # BrickItem's single touch — no more runaway summed-Count headline numbers.
    obj = dict(activity.by_object)
    assert obj["StoneItem"] == 2
    assert obj["IronOreItem"] == 2
    assert obj["BrickItem"] == 1
    assert activity.by_object[-1] == ("BrickItem", 1)
    # to_dict / from_dict round-trip preserves the ranked shape.
    from eco_mcp_app.world import WorldActivity

    again = WorldActivity.from_dict(activity.to_dict())
    assert again.total_events == activity.total_events
    assert again.categories == activity.categories
    assert again.timeline == activity.timeline
    assert again.hotspots == activity.hotspots


def test_apply_citizen_names_resolves_and_falls_back() -> None:
    acc = WorldAccumulator()
    acc.by_citizen = {"129312": 5, "999999": 2}
    apply_citizen_names(acc, {"129312": "coilysiren"})
    assert acc.by_citizen["coilysiren"] == 5
    assert acc.by_citizen["Citizen #999999"] == 2


@pytest.mark.asyncio
@respx.mock
async def test_fetch_world_merges_actions_and_joins_names() -> None:
    _mock_all_actions(
        {
            "ConstructOrDeconstruct": _CONSTRUCT_CSV,
            "PlaceOrPickUpObject": _PLACE_CSV,
            "TampRoad": _TAMP_CSV,
            "DigOrMine": _DIG_CSV,
        }
    )
    respx.get(CITIZENS_URL).mock(return_value=httpx.Response(200, json=_CITIZENS_JSON))

    activity = await fetch_world(base_url=BASE, api_key="secret", cache_ttl_s=0)
    # 3 construct + 2 place + 1 tamp + 2 dig = 8 events.
    assert activity.total_events == 8
    keys = activity.category_keys
    assert {"construction", "objects", "roads", "extraction"} <= set(keys)
    # Citizen ids resolved to names. coilysiren (129312): 1 construct + 2 place = 3.
    by_citizen = dict(activity.by_citizen)
    assert by_citizen["coilysiren"] == 3
    assert by_citizen["redwood"] == 3  # 129580: 1 construct + 2 dig
    assert activity.warnings == []
    assert activity.per_action_counts["ConstructOrDeconstruct"] == 3


@pytest.mark.asyncio
@respx.mock
async def test_fetch_world_tolerates_partial_failures() -> None:
    _mock_all_actions({"ConstructOrDeconstruct": _CONSTRUCT_CSV})
    # Override two actions with faults.
    respx.get(_action_url("TampRoad")).mock(return_value=httpx.Response(401))
    respx.get(_action_url("ObjectExplosion")).mock(side_effect=httpx.ConnectError("nope"))
    respx.get(CITIZENS_URL).mock(return_value=httpx.Response(200, json=_CITIZENS_JSON))

    activity = await fetch_world(base_url=BASE, api_key=None, cache_ttl_s=0)
    assert activity.per_action_counts["ConstructOrDeconstruct"] == 3
    assert any("TampRoad" in w and "401" in w for w in activity.warnings)
    assert any("ObjectExplosion" in w for w in activity.warnings)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_world_shows_ids_when_join_unavailable() -> None:
    _mock_all_actions({"ConstructOrDeconstruct": _CONSTRUCT_CSV})
    respx.get(CITIZENS_URL).mock(return_value=httpx.Response(404))

    activity = await fetch_world(base_url=BASE, api_key=None, cache_ttl_s=0)
    by_citizen = dict(activity.by_citizen)
    assert by_citizen["Citizen #129312"] == 1


@pytest.mark.asyncio
@respx.mock
async def test_fetch_world_cache_hits_within_ttl() -> None:
    _mock_all_actions({"ConstructOrDeconstruct": _CONSTRUCT_CSV})
    route = respx.get(_action_url("ConstructOrDeconstruct")).mock(
        return_value=httpx.Response(200, text=_CONSTRUCT_CSV)
    )
    respx.get(CITIZENS_URL).mock(return_value=httpx.Response(200, json=_CITIZENS_JSON))

    a1 = await fetch_world(base_url=BASE, api_key="k", cache_ttl_s=60)
    a2 = await fetch_world(base_url=BASE, api_key="k", cache_ttl_s=60)
    assert a1.total_events == a2.total_events
    assert route.call_count == 1  # second call served from SQLite


@pytest.mark.asyncio
@respx.mock
async def test_fetch_world_empty_server_degrades() -> None:
    _mock_all_actions()
    respx.get(CITIZENS_URL).mock(return_value=httpx.Response(200, json=[]))
    activity = await fetch_world(base_url=BASE, api_key="k", cache_ttl_s=0)
    assert activity.total_events == 0
    assert activity.categories == []
    assert activity.warnings == []


@pytest.mark.asyncio
@respx.mock
async def test_tool_call_returns_two_text_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECO_ADMIN_API_KEY", "k")
    _mock_all_actions({"ConstructOrDeconstruct": _CONSTRUCT_CSV, "DigOrMine": _DIG_CSV})
    respx.get(CITIZENS_URL).mock(return_value=httpx.Response(200, json=_CITIZENS_JSON))

    mcp = build_server()
    handler = mcp.request_handlers[mt.CallToolRequest]
    req = mt.CallToolRequest(
        method="tools/call",
        params=mt.CallToolRequestParams(
            name="get_world",
            arguments={"server": "eco.example.com:3001"},
        ),
    )
    result = await handler(req)
    blocks = result.root.content
    assert len(blocks) == 2
    assert isinstance(blocks[0], mt.TextContent)
    assert "World activity" in blocks[0].text
    assert result.root.meta is None


@pytest.mark.asyncio
async def test_list_tools_includes_get_world() -> None:
    mcp = build_server()
    handler = mcp.request_handlers[mt.ListToolsRequest]
    result = await handler(mt.ListToolsRequest(method="tools/list"))
    names = {tool.name for tool in result.root.tools}
    assert "get_world" in names
