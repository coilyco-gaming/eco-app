"""Tests for host-agnostic trade watchers (eco-app#52).

Covers:
  - Query validation + normalization (kinds, price op/threshold, bad specs).
  - Match logic for every kind: item, store, trader, price under/over.
  - Feed vs display semantics: feed is new-since-last-seen, display is the
    current matching state.
  - The last-seen advance: a second evaluation of the same ledger surfaces no
    fresh feed hits, and peek mode (`advance=False`) never consumes the mark.
  - SQLite persistence: create / list / remove survive a fresh connection
    (the store is opened per call), schema is created idempotently.
  - `respx`-mocked end-to-end evaluate through `fetch_ledger` + the MCP tool
    wiring (create / list / evaluate / remove) and the SPA data endpoint.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import mcp.types as mt
import pytest
import respx
from starlette.testclient import TestClient

from eco_mcp_app import trades as trades_mod
from eco_mcp_app.http_app import create_app
from eco_mcp_app.server import build_server
from eco_mcp_app.watchers import (
    WatcherError,
    build_query,
    create_watcher,
    evaluate_all,
    evaluate_watcher,
    get_watcher,
    list_watchers,
    normalize_op,
    remove_watcher,
    trade_matches,
)

CURRENCY_URL = "http://eco.example.com:3001/api/v1/exporter/actions?actionName=CurrencyTrade"
BARTER_URL = "http://eco.example.com:3001/api/v1/exporter/actions?actionName=BarterTrade"
CITIZENS_URL = "http://eco.example.com:3001/api/v1/citizens"
BASE = "http://eco.example.com:3001"

_CITIZENS_JSON = [
    {"id": 129312, "name": "coilysiren"},
    {"id": 130409, "name": "ekans"},
    {"id": 129580, "name": "redwood"},
]

# Same cycle-13 column order as test_trades. Three iron trades at unit prices
# 25 / 28 / 2.0 and one wheat trade, so a "iron ingot under 2.5" price watcher
# catches exactly the cheap iron row.
_CURRENCY_CSV = (
    "BankAccount,Currency,CurrencyAmount,NumberOfItems,BoughtOrSold,ShopOwner,"
    "Buyer,Seller,WorldObjectItem,ItemUsed,Citizen,ActionLocation,Count,Time\n"
    '"ekans account",Credit,250.0,10,33,130409,129312,130409,IronStore,'
    'IronIngotItem,129312,"1,2,3",1,300000\n'
    '"ekans account",Credit,140.0,5,33,130409,129580,130409,IronStore,'
    'IronIngotItem,129580,"1,2,3",1,200000\n'
    '"cheap account",Credit,20.0,10,33,130409,129580,130409,IronStore,'
    'IronIngotItem,129580,"1,2,3",1,250000\n'
    '"coilysiren account",Credit,225.0,45,32,129312,129569,129312,WheatStall,'
    'WheatItem,129569,"4,5,6",1,100000\n'
)

_BARTER_EMPTY = "Buyer,Seller,ItemUsed,NumberOfItems,Count,Time\n"


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the watcher SQLite store (and trades cache) at a temp dir.

    `default_cache_dir` reads ECO_MCP_CACHE_DIR, so relocating it isolates the
    watcher DB per test. The trades TTL cache is module-level, so clear it too.
    """
    monkeypatch.setenv("ECO_MCP_CACHE_DIR", str(tmp_path / "cache"))
    trades_mod._trades_cache.clear()
    yield
    trades_mod._trades_cache.clear()


# ---------------------------------------------------------------------------
# Query validation
# ---------------------------------------------------------------------------


def test_normalize_op_aliases() -> None:
    assert normalize_op("under") == "under"
    assert normalize_op("<") == "under"
    assert normalize_op("below") == "under"
    assert normalize_op("over") == "over"
    assert normalize_op(">=") == "over"
    assert normalize_op("sideways") is None
    assert normalize_op(None) is None


def test_build_query_validates() -> None:
    q = build_query("item", "IronIngot")
    assert q.kind == "item" and q.value == "IronIngot"

    price = build_query("price", "iron ingot", op="below", threshold=2.5)
    assert price.kind == "price" and price.op == "under" and price.threshold == 2.5

    with pytest.raises(WatcherError):
        build_query("nonsense", "x")
    with pytest.raises(WatcherError):
        build_query("item", "   ")
    with pytest.raises(WatcherError):
        build_query("price", "iron", op=None, threshold=2.5)
    with pytest.raises(WatcherError):
        build_query("price", "iron", op="under", threshold=None)


def test_query_describe() -> None:
    assert build_query("price", "IronIngotItem", op="under", threshold=2.5).describe() == (
        "Iron Ingot under 2.5"
    )
    assert build_query("trader", "ekans").describe() == "trader: ekans"


# ---------------------------------------------------------------------------
# Match logic
# ---------------------------------------------------------------------------


def _trade(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "tradeType": "CurrencyTrade",
        "time": 100.0,
        "day": 1.0,
        "buyer": "coilysiren",
        "seller": "ekans",
        "shopOwner": "ekans",
        "item": "IronIngotItem",
        "quantity": 10.0,
        "currency": "Credit",
        "currencyAmount": 250.0,
        "unitPrice": 25.0,
        "store": "IronStore",
        "location": "1,2,3",
        "direction": "sell",
    }
    base.update(over)
    return base


def test_trade_matches_item_by_raw_and_pretty() -> None:
    t = _trade()
    assert trade_matches(build_query("item", "IronIngot"), t)
    # Prettified form ("Iron Ingot") also matches.
    assert trade_matches(build_query("item", "iron ingot"), t)
    assert not trade_matches(build_query("item", "copper"), t)


def test_trade_matches_store_and_trader() -> None:
    t = _trade()
    assert trade_matches(build_query("store", "ironstore"), t)
    assert not trade_matches(build_query("store", "wheat"), t)
    assert trade_matches(build_query("trader", "ekans"), t)
    assert trade_matches(build_query("trader", "coilysiren"), t)
    assert not trade_matches(build_query("trader", "redwood"), t)


def test_trade_matches_price_threshold() -> None:
    cheap = _trade(unitPrice=2.0)
    dear = _trade(unitPrice=25.0)
    under = build_query("price", "iron ingot", op="under", threshold=2.5)
    over = build_query("price", "iron ingot", op="over", threshold=2.5)
    assert trade_matches(under, cheap)
    assert not trade_matches(under, dear)
    assert trade_matches(over, dear)
    assert not trade_matches(over, cheap)
    # A different item never matches even at the right price.
    assert not trade_matches(under, _trade(item="WheatItem", unitPrice=1.0))
    # Barter / unpriced rows never match a price watcher.
    assert not trade_matches(under, _trade(unitPrice=None))


# ---------------------------------------------------------------------------
# Feed vs display + last-seen advance
# ---------------------------------------------------------------------------


def _ledger_rows() -> list[dict[str, object]]:
    return [
        _trade(time=300000.0, unitPrice=25.0),
        _trade(time=250000.0, unitPrice=2.0),
        _trade(time=200000.0, unitPrice=28.0),
        _trade(time=100000.0, item="WheatItem", unitPrice=5.0),
    ]


def test_evaluate_watcher_feed_and_display() -> None:
    watcher = create_watcher(build_query("item", "iron ingot"))
    hit = evaluate_watcher(watcher, _ledger_rows())
    # Display: all three iron rows are the current matching state, newest first.
    assert len(hit.matches) == 3
    assert [m["time"] for m in hit.matches] == [300000.0, 250000.0, 200000.0]
    # Feed: last_seen starts at 0, so every current match is a fresh feed hit.
    assert len(hit.feed) == 3
    # The mark advances to the newest matching row.
    assert hit.new_last_seen == 300000.0
    d = hit.to_dict()
    assert d["display"]["matchCount"] == 3
    assert d["display"]["bestUnitPrice"] == 2.0
    assert d["feedCount"] == 3


def test_evaluate_all_advances_then_quiets() -> None:
    create_watcher(build_query("item", "iron ingot"))
    rows = _ledger_rows()
    first = evaluate_all(rows, advance=True)
    assert first[0].to_dict()["feedCount"] == 3
    # Second pass over the *same* ledger: the mark has advanced past every row,
    # so the feed is empty but the display still shows the full matching state.
    second = evaluate_all(rows, advance=True)
    assert second[0].to_dict()["feedCount"] == 0
    assert second[0].to_dict()["display"]["matchCount"] == 3


def test_evaluate_all_peek_does_not_consume() -> None:
    create_watcher(build_query("item", "iron ingot"))
    rows = _ledger_rows()
    a = evaluate_all(rows, advance=False)
    b = evaluate_all(rows, advance=False)
    # Peek mode never advances the mark, so both passes see the same feed.
    assert a[0].to_dict()["feedCount"] == 3
    assert b[0].to_dict()["feedCount"] == 3
    # And the stored watcher's mark is untouched.
    assert list_watchers()[0].last_seen == 0.0


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_create_list_remove_roundtrip() -> None:
    assert list_watchers() == []
    w = create_watcher(
        build_query("price", "iron ingot", op="under", threshold=2.5), label="cheap iron"
    )
    fetched = get_watcher(w.id)
    assert fetched is not None
    assert fetched.label == "cheap iron"
    assert fetched.query.threshold == 2.5
    assert len(list_watchers()) == 1
    assert remove_watcher(w.id) is True
    assert remove_watcher(w.id) is False
    assert list_watchers() == []


# ---------------------------------------------------------------------------
# End-to-end: fetch_ledger + MCP tool wiring
# ---------------------------------------------------------------------------


async def _call(handler, name: str, arguments: dict[str, object]) -> mt.CallToolResult:
    req = mt.CallToolRequest(
        method="tools/call",
        params=mt.CallToolRequestParams(name=name, arguments=arguments),
    )
    result = await handler(req)
    return result.root  # type: ignore[return-value]


@pytest.mark.asyncio
@respx.mock
async def test_tool_create_list_evaluate_remove(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECO_ADMIN_API_KEY", "k")
    respx.get(CURRENCY_URL).mock(return_value=httpx.Response(200, text=_CURRENCY_CSV))
    respx.get(BARTER_URL).mock(return_value=httpx.Response(200, text=_BARTER_EMPTY))
    respx.get(CITIZENS_URL).mock(return_value=httpx.Response(200, json=_CITIZENS_JSON))

    mcp = build_server()
    handler = mcp.request_handlers[mt.CallToolRequest]

    # Create a price watcher for cheap iron.
    created = await _call(
        handler,
        "trade_watchers",
        {
            "action": "create",
            "kind": "price",
            "value": "iron ingot",
            "op": "under",
            "threshold": 2.5,
        },
    )
    import json

    created_payload = json.loads(created.content[1].text)
    wid = created_payload["watcher"]["id"]
    assert created_payload["watcher"]["op"] == "under"

    # List shows it.
    listed = await _call(handler, "trade_watchers", {"action": "list"})
    listed_payload = json.loads(listed.content[1].text)
    assert any(w["id"] == wid for w in listed_payload["watchers"])

    # Evaluate against the live ledger — the one cheap iron row (unit price 2.0)
    # is a feed hit and the current match.
    evaluated = await _call(
        handler, "trade_watchers", {"action": "evaluate", "server": "eco.example.com:3001"}
    )
    eval_payload = json.loads(evaluated.content[1].text)
    hit = next(h for h in eval_payload["hits"] if h["id"] == wid)
    assert hit["display"]["matchCount"] == 1
    assert hit["feedCount"] == 1
    assert hit["display"]["bestUnitPrice"] == 2.0

    # A second evaluate advanced the mark, so the feed is now empty.
    again = await _call(
        handler, "trade_watchers", {"action": "evaluate", "server": "eco.example.com:3001"}
    )
    again_hit = next(h for h in json.loads(again.content[1].text)["hits"] if h["id"] == wid)
    assert again_hit["feedCount"] == 0

    # Remove it.
    removed = await _call(handler, "trade_watchers", {"action": "remove", "id": wid})
    assert json.loads(removed.content[1].text)["removed"] is True


@pytest.mark.asyncio
async def test_tool_create_rejects_bad_price() -> None:
    mcp = build_server()
    handler = mcp.request_handlers[mt.CallToolRequest]
    result = await _call(
        handler, "trade_watchers", {"action": "create", "kind": "price", "value": "iron"}
    )
    assert result.isError is True


@pytest.mark.asyncio
async def test_create_summary_uses_the_supplied_label() -> None:
    """An explicit label wins in the create summary too (eco-app#239).

    `list` and `evaluate` already lead with the stored label; `create` was the
    odd one out, printing only the generated predicate description.
    """
    mcp = build_server()
    handler = mcp.request_handlers[mt.CallToolRequest]
    result = await _call(
        handler,
        "trade_watchers",
        {
            "action": "create",
            "kind": "price",
            "value": "CementItem",
            "op": "under",
            "threshold": 1,
            "label": "qa-probe-cement",
        },
    )
    markdown = result.content[0].text
    assert "qa-probe-cement" in markdown
    # The predicate stays visible alongside the label.
    assert "under 1" in markdown


@pytest.mark.asyncio
async def test_create_summary_falls_back_to_the_description() -> None:
    """With no label supplied, the generated description is not doubled up."""
    mcp = build_server()
    handler = mcp.request_handlers[mt.CallToolRequest]
    result = await _call(
        handler,
        "trade_watchers",
        {"action": "create", "kind": "item", "value": "iron ingot"},
    )
    markdown = result.content[0].text
    assert markdown.count("iron ingot") == 1
    assert "(" not in markdown.split("watching", 1)[1]


@pytest.mark.asyncio
async def test_list_tools_includes_watchers() -> None:
    mcp = build_server()
    handler = mcp.request_handlers[mt.ListToolsRequest]
    result = await handler(mt.ListToolsRequest(method="tools/list"))
    names = {tool.name for tool in result.root.tools}
    assert "trade_watchers" in names


@respx.mock
def test_spa_watchers_endpoint_peeks(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """`/preview/watchers.json` evaluates in peek mode without consuming feeds."""
    monkeypatch.setenv("ECO_MCP_CACHE_DIR", str(tmp_path / "cache2"))
    monkeypatch.setenv("ECO_ADMIN_API_KEY", "k")
    trades_mod._trades_cache.clear()
    respx.get(CURRENCY_URL).mock(return_value=httpx.Response(200, text=_CURRENCY_CSV))
    respx.get(BARTER_URL).mock(return_value=httpx.Response(200, text=_BARTER_EMPTY))
    respx.get(CITIZENS_URL).mock(return_value=httpx.Response(200, json=_CITIZENS_JSON))

    create_watcher(build_query("item", "iron ingot"), label="all iron")

    # ECO_INFO_URL is captured at import, so target the mocked server via ?server=.
    client = TestClient(create_app())
    resp = client.get("/preview/watchers.json?server=eco.example.com:3001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["view"] == "watcher_hits"
    assert body["advanced"] is False
    hit = body["hits"][0]
    assert hit["display"]["matchCount"] == 3
    # Peek did not consume the feed, so a re-poll still shows the same hits.
    resp2 = client.get("/preview/watchers.json?server=eco.example.com:3001")
    assert resp2.json()["hits"][0]["feedCount"] == hit["feedCount"]
