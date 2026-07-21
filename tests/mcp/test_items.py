"""Tests for the item index + per-item pivot (eco-app#81).

Covers:
  - build_item_index merges the trades ledger's `by_item` and the crafting
    atlas's `by_item` into one ranked directory (union of both namespaces).
  - fetch_item_index over respx-mocked trade + craft CSVs.
  - fetch_item_pivot filters the trade leg to one item and re-streams the craft
    CSVs for that item, newest first, with citizen ids joined to names.
  - An item with no history yields a clean empty pivot, not an error.
  - The dedicated `/preview/items.json` + `/preview/item.json` routes.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from eco_mcp_app import items as items_mod
from eco_mcp_app import trades as trades_mod
from eco_mcp_app.http_app import create_app
from eco_mcp_app.items import build_item_index, fetch_item_index, fetch_item_pivot

BASE = "http://eco.example.com:3001"
CURRENCY_URL = f"{BASE}/api/v1/exporter/actions?actionName=CurrencyTrade"
BARTER_URL = f"{BASE}/api/v1/exporter/actions?actionName=BarterTrade"
CRAFT_URL = f"{BASE}/api/v1/exporter/actions?actionName=ItemCraftedAction"
HARVEST_URL = f"{BASE}/api/v1/exporter/actions?actionName=HarvestOrHunt"
CHOP_URL = f"{BASE}/api/v1/exporter/actions?actionName=ChopTree"
DIG_URL = f"{BASE}/api/v1/exporter/actions?actionName=DigOrMine"
CITIZENS_URL = f"{BASE}/api/v1/citizens"
STORES_URL = f"{BASE}/api/v1/stores"
INFO_URL = f"{BASE}/info"

_CITIZENS_JSON = [
    {"id": 129312, "name": "coilysiren"},
    {"id": 130409, "name": "ekans"},
    {"id": 129580, "name": "redwood"},
]

# CurrencyTrade cycle-13 column order. Row 1: coilysiren sells 2 Beet to ekans
# for 20 (unit 10, day ~3.5). Row 2: ekans sells 10 IronIngot to redwood for 250.
_CURRENCY_CSV = (
    "BankAccount,Currency,CurrencyAmount,NumberOfItems,BoughtOrSold,ShopOwner,"
    "Buyer,Seller,WorldObjectItem,ItemUsed,Citizen,ActionLocation,Count,Time\n"
    '"acct",Credit,20.0,2,33,129312,130409,129312,StoreItem,BeetItem,129312,"1,2,3",1,300000\n'
    '"acct",Credit,250.0,10,33,130409,129580,130409,StoreItem,'
    'IronIngotItem,130409,"1,2,3",1,200000\n'
)
_BARTER_EMPTY = "Buyer,Seller,ItemUsed,NumberOfItems,Count,Time\n"

# ItemCraftedAction: ekans crafts 1 Beet at an anvil (day ~2.9), coilysiren
# crafts 3 IronIngot iterations (day ~1.2). WorldObjectItem is the station,
# ItemUsed the produced item, Count is 1 per event row. The final row is a
# server-side hourly rollup (Count > 1): its labels come from its first merged
# event, so it counts as exactly 1 proven IronIngot iteration, never the
# merged 810 (eco-app#131).
_CRAFT_CSV = (
    "ActionLocation,WorldObjectItem,Citizen,ItemUsed,"
    "OverrideHierarchyActionsToConsumer,Count,Time\n"
    '"1,2,3",AnvilItem,130409,BeetItem,false,1,250000\n'
    '"1,2,3",AnvilItem,129312,IronIngotItem,false,1,100000\n'
    '"1,2,3",AnvilItem,129312,IronIngotItem,false,1,100100\n'
    '"1,2,3",AnvilItem,129312,IronIngotItem,false,1,100200\n'
    '"1,2,3",AnvilItem,129312,IronIngotItem,false,810,110000\n'
)
_HARVEST_EMPTY = (
    "Species,DamagedOrDestroyed,DestroyedByBlock,CaloriesToConsume,"
    "Position,Citizen,ActionLocation,Count,Time\n"
)
_CHOP_EMPTY = (
    "OnGround,Felled,Species,BranchesTargeted,GrowthPercent,CaloriesToConsume,"
    "ToolUsed,Position,Citizen,ActionLocation,Count,Time\n"
)
_DIG_EMPTY = "Position,Citizen,Count,Time\n"


@pytest.fixture(autouse=True)
def _isolated_caches(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # The crafting atlas caches to a SQLite under ECO_CACHE_DIR; the trades
    # ledger + item pivot cache in-process. Isolate all three per test.
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("ECO_CACHE_DIR", tmp)
        trades_mod._trades_cache.clear()
        items_mod._clear_cache()
        yield
        trades_mod._trades_cache.clear()
        items_mod._clear_cache()


def _mock_all() -> None:
    respx.get(CURRENCY_URL).mock(return_value=httpx.Response(200, text=_CURRENCY_CSV))
    respx.get(BARTER_URL).mock(return_value=httpx.Response(200, text=_BARTER_EMPTY))
    respx.get(CRAFT_URL).mock(return_value=httpx.Response(200, text=_CRAFT_CSV))
    respx.get(HARVEST_URL).mock(return_value=httpx.Response(200, text=_HARVEST_EMPTY))
    respx.get(CHOP_URL).mock(return_value=httpx.Response(200, text=_CHOP_EMPTY))
    respx.get(DIG_URL).mock(return_value=httpx.Response(200, text=_DIG_EMPTY))
    respx.get(CITIZENS_URL).mock(return_value=httpx.Response(200, json=_CITIZENS_JSON))
    # The pivot now folds a supply/demand summary off the logistics spine (the
    # live shelf is reset-gated, so a 404 degrades to history) and reads the
    # world clock off /info.
    respx.get(STORES_URL).mock(return_value=httpx.Response(404))
    respx.get(INFO_URL).mock(return_value=httpx.Response(200, json={"TimeSinceStart": 305000}))


def test_build_item_index_merges_trade_and_craft_namespaces() -> None:
    index = build_item_index(
        ledger_by_item=[("BeetItem", 1, 20.0), ("IronIngotItem", 1, 250.0)],
        atlas_by_item=[("BeetItem", 5.0), ("IronIngotItem", 810.0), ("OakSpecies", 300.0)],
        fetched_at_iso="now",
        source_base_url=BASE,
    )
    by_id = {r["item"]: r for r in index.items}
    assert index.to_dict()["totalItems"] == 3
    # Harvest-only item shows up with zero trades.
    assert by_id["OakSpecies"] == {
        "item": "OakSpecies",
        "tradeCount": 0,
        "tradeVolume": 0.0,
        "craftCount": 300.0,
    }
    assert by_id["BeetItem"]["tradeCount"] == 1
    assert by_id["BeetItem"]["craftCount"] == 5.0
    # Ranked by total activity: IronIngot (1 + 810) leads Beet (1 + 5).
    assert index.items[0]["item"] == "IronIngotItem"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_item_index_unions_both_exporters() -> None:
    _mock_all()
    index = await fetch_item_index(base_url=BASE, api_key="secret")
    by_id = {r["item"]: r for r in index.items}
    assert set(by_id) == {"BeetItem", "IronIngotItem"}
    assert by_id["IronIngotItem"] == {
        "item": "IronIngotItem",
        "tradeCount": 1,
        "tradeVolume": 250.0,
        # Three per-event iterations plus the rollup row's one proven
        # representative iteration - a confirmed floor, not the merged 810
        # (eco-app#131).
        "craftCount": 4.0,
    }
    assert by_id["BeetItem"]["tradeVolume"] == 20.0
    assert index.items[0]["item"] == "IronIngotItem"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_item_pivot_trades_and_crafts_for_one_item() -> None:
    _mock_all()
    pivot = await fetch_item_pivot("BeetItem", base_url=BASE, api_key="secret", cache_ttl_s=0)
    assert pivot.item == "BeetItem"

    assert pivot.trade_count == 1
    assert pivot.trade_volume == 20.0
    (trade,) = pivot.trades
    assert trade["seller"] == "coilysiren"
    assert trade["buyer"] == "ekans"
    assert trade["quantity"] == 2
    assert trade["unitPrice"] == 10.0

    assert pivot.craft_count == 1
    assert pivot.craft_quantity == 1.0
    (craft,) = pivot.crafts
    assert craft["actionType"] == "ItemCraftedAction"
    assert craft["citizen"] == "ekans"
    assert craft["quantity"] == 1.0
    assert craft["station"] == "AnvilItem"

    # Merged reverse-chrono feed: trade (t=300000) newest, craft (t=250000) next.
    assert [(row["kind"], row["runCount"]) for row in pivot.feed] == [("trade", 1), ("craft", 1)]
    assert pivot.feed[0]["buyer"] == "ekans"
    assert pivot.feed[1]["actor"] == "ekans"

    # World clock read off /info so the SPA can age events against real "now".
    assert pivot.world_clock_s == 305000

    # Actionable summary: who makes it (ekans, 1 iteration) and who sells it
    # (coilysiren's history-derived shelf, since the live shelf 404s here).
    assert pivot.summary["crafters"] == [{"name": "ekans", "quantity": 1.0, "events": 1}]
    assert pivot.summary["supply"]["storeCount"] == 1
    assert pivot.summary["live"] is False


@pytest.mark.asyncio
@respx.mock
async def test_fetch_item_pivot_clamps_rollup_craft_rows() -> None:
    """The 810-iteration hourly rollup counts as its one proven iteration."""
    _mock_all()
    pivot = await fetch_item_pivot("IronIngotItem", base_url=BASE, api_key="secret", cache_ttl_s=0)
    assert pivot.craft_count == 4
    assert pivot.craft_quantity == 4.0
    assert all(c["quantity"] == 1.0 for c in pivot.crafts)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_item_pivot_unknown_item_is_empty_not_error() -> None:
    _mock_all()
    pivot = await fetch_item_pivot("NopeItem", base_url=BASE, api_key="secret", cache_ttl_s=0)
    assert pivot.trade_count == 0
    assert pivot.craft_count == 0
    assert pivot.trades == []
    assert pivot.crafts == []
    assert pivot.feed == []
    assert pivot.summary["crafters"] == []


def test_build_item_feed_compresses_consecutive_repeats() -> None:
    from eco_mcp_app.items import build_item_feed

    # Rechim crafts 1 Hewn Log at a Carpentry Table five times in a row, then
    # once at a different station, then a trade. Same (actor, verb, station) runs
    # collapse; the station switch and the trade break the run.
    crafts = [
        {
            "actionType": "ItemCraftedAction",
            "time": t,
            "day": t / 86400,
            "citizen": "Rechim",
            "station": "CarpentryTableItem",
            "quantity": 1,
        }
        for t in (500, 400, 300, 200, 100)
    ]
    crafts.append(
        {
            "actionType": "ItemCraftedAction",
            "time": 90,
            "day": 90 / 86400,
            "citizen": "Rechim",
            "station": "SawmillItem",
            "quantity": 1,
        }
    )
    trades = [
        {
            "tradeType": "CurrencyTrade",
            "time": 600,
            "day": 600 / 86400,
            "buyer": "b",
            "seller": "s",
            "shopOwner": "s",
            "item": "HewnLogItem",
            "quantity": 2,
            "currency": "Credit",
            "currencyAmount": 8,
            "unitPrice": 4,
            "store": "StoreItem",
            "location": "",
            "direction": "sell",
        }
    ]
    feed, truncated = build_item_feed(trades, crafts)
    assert truncated is False
    # trade (t=600), 5 collapsed carpentry crafts (t=500..100), 1 sawmill craft.
    assert [(r["kind"], r["runCount"]) for r in feed] == [("trade", 1), ("craft", 5), ("craft", 1)]
    run = feed[1]
    assert run["quantity"] == 5  # 1 x 5 summed
    assert run["time"] == 500  # newest in the run
    assert run["spanSeconds"] == 400  # 500 - 100

    # The cap collapses to the compressed row count, and flags truncation.
    tiny, tiny_trunc = build_item_feed(trades, crafts, max_rows=1)
    assert len(tiny) == 1 and tiny_trunc is True


@respx.mock
def test_preview_routes_serve_index_and_pivot() -> None:
    _mock_all()
    client = TestClient(create_app())

    r = client.get("/preview/items.json", params={"server": BASE})
    assert r.status_code == 200
    payload = r.json()
    assert payload["totalItems"] == 2
    assert {row["item"] for row in payload["items"]} == {"BeetItem", "IronIngotItem"}

    r = client.get("/preview/item.json", params={"server": BASE, "item": "BeetItem"})
    assert r.status_code == 200
    pivot = r.json()
    assert pivot["item"] == "BeetItem"
    assert pivot["tradeCount"] == 1
    assert pivot["crafts"][0]["citizen"] == "ekans"

    # The item param is required.
    r = client.get("/preview/item.json", params={"server": BASE})
    assert r.status_code == 400
