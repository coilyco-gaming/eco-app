"""Tests for the social / chat surface aggregator + redaction (eco-app#63).

Covers:
  - Folding ChatSent / ReputationTransfer / FirstLogin / Play CSVs into the
    right shapes (chat samples, reputation edges, activity by in-game day).
  - **Redaction is load-bearing**: on the public path neither raw player names
    nor raw message bodies are emitted — names become stable handles and known
    names inside chat text are scrubbed to those handles.
  - Names-in-the-clear is operator-gated (default-deny): reveal_names only takes
    effect when ECO_SOCIAL_ALLOW_NAMES is set.
  - respx-mocked fetch merges the four actions and joins ids to names.
  - Missing-endpoint (401 / connect error) becomes a non-fatal warning.
  - Empty CSVs produce a clean "no social activity" surface.
  - The /preview/social.json data plane is always redacted.
  - Tool wiring returns markdown + JSON blocks + a `_meta.ui` fragment.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator

import httpx
import mcp.types as mt
import pytest
import respx
from starlette.testclient import TestClient

from eco_mcp_app import social as social_mod
from eco_mcp_app.http_app import create_app
from eco_mcp_app.server import build_server
from eco_mcp_app.social import (
    SocialSurface,
    build_surface,
    fetch_social,
    hash_handle,
    parse_activity_rows,
    parse_chat_rows,
    parse_reputation_rows,
    social_markdown,
    social_template_context,
)

BASE = "http://eco.example.com:3001"
CHAT_URL = f"{BASE}/api/v1/exporter/actions?actionName=ChatSent"
PLAY_URL = f"{BASE}/api/v1/exporter/actions?actionName=Play"
LOGIN_URL = f"{BASE}/api/v1/exporter/actions?actionName=FirstLogin"
REP_URL = f"{BASE}/api/v1/exporter/actions?actionName=ReputationTransfer"
CITIZENS_URL = f"{BASE}/api/v1/citizens"

_CITIZENS_JSON = [
    {"id": 129312, "name": "coilysiren"},
    {"id": 130409, "name": "ekans"},
    {"id": 129580, "name": "redwood"},
]

# Author id, channel/tag, message, then the trailing Count/Time the exporter
# appends to every action row.
_CHAT_CSV = (
    "Citizen,Tag,Message,Count,Time\n"
    '129312,#general,"selling iron, ping ekans please",1,300000\n'
    '130409,#trade,"anyone need wood?",1,200000\n'
    '129312,#general,"gg",1,260000\n'
)
_REP_CSV = (
    "Citizen,ReceiverCitizen,Amount,Count,Time\n"
    "129312,130409,5.0,1,250000\n"
    "129580,130409,3.0,1,150000\n"
)
_LOGIN_CSV = "Citizen,Count,Time\n130409,1,100000\n"
_PLAY_CSV = "Citizen,Count,Time\n129312,1,50000\n129580,1,60000\n"


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    social_mod._social_cache.clear()
    yield
    social_mod._social_cache.clear()


def _rows(csv_text: str) -> list[list[str]]:
    return list(csv.reader(csv_text.splitlines()))


def _parse_all(surface: SocialSurface) -> tuple[list, list, list]:
    chat: list = []
    edges: list = []
    activity: list = []
    parse_chat_rows(_rows(_CHAT_CSV), surface, chat)
    parse_reputation_rows(_rows(_REP_CSV), surface, edges)
    parse_activity_rows("FirstLogin", _rows(_LOGIN_CSV), surface, activity)
    parse_activity_rows("Play", _rows(_PLAY_CSV), surface, activity)
    return chat, edges, activity


NAME_MAP = {"129312": "coilysiren", "130409": "ekans", "129580": "redwood"}


def test_parse_and_fold_shapes() -> None:
    surface = SocialSurface(fetched_at_iso="t", source_base_url="b")
    chat, edges, activity = _parse_all(surface)
    build_surface(surface, chat, edges, activity, NAME_MAP, show_names=True)

    assert surface.total_chat == 3
    assert surface.total_reputation_transfers == 2
    assert surface.total_first_logins == 1
    assert surface.total_play_events == 2
    # Chat bucketed by in-game day (Time / 86400).
    assert dict(surface.chat_by_day) == {2: 1, 3: 2}
    # Busiest channel is #general (2 of 3 messages).
    assert surface.chat_by_channel[0] == ("#general", 2)
    # ekans received 8 reputation across two transfers → most-repped.
    assert surface.top_reputation_receivers[0] == ("ekans", pytest.approx(8.0))
    # Directed edges carry the amount + count.
    edge = next(e for e in surface.reputation_edges if e["source"] == "coilysiren")
    assert edge["target"] == "ekans"
    assert edge["amount"] == pytest.approx(5.0)
    # New arrival from FirstLogin.
    assert surface.new_arrivals == [{"label": "ekans", "day": 1}]


def test_public_path_redacts_names_and_message_bodies() -> None:
    """The load-bearing guarantee: no raw name / raw body on the public path."""
    surface = SocialSurface(fetched_at_iso="t", source_base_url="b")
    chat, edges, activity = _parse_all(surface)
    build_surface(surface, chat, edges, activity, NAME_MAP, show_names=False)

    blob = json.dumps(surface.to_dict())
    # Not one real player name survives anywhere in the serialized payload —
    # not as an author, not as a graph node, not inside a chat body.
    for real_name in ("coilysiren", "ekans", "redwood"):
        assert real_name not in blob, f"{real_name!r} leaked onto the public path"
    # The redaction flag is honest.
    assert surface.redacted is True
    # Authors + graph nodes are stable handles.
    assert surface.recent_chat[0]["author"] == hash_handle("coilysiren")
    assert surface.top_reputation_receivers[0][0] == hash_handle("ekans")
    # The "ping ekans" body was scrubbed to ekans's handle in place.
    ping = next(m for m in surface.recent_chat if "ping" in m["message"])
    assert hash_handle("ekans") in ping["message"]
    assert "ekans" not in ping["message"].replace(hash_handle("ekans"), "")


def test_operator_mode_shows_names_only_when_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default-deny: reveal_names alone does nothing without the env gate.
    monkeypatch.delenv(social_mod.NAMES_ALLOW_ENV, raising=False)
    assert social_mod.effective_show_names(reveal_names=True) is False
    # Gate lifted → names show.
    monkeypatch.setenv(social_mod.NAMES_ALLOW_ENV, "1")
    assert social_mod.effective_show_names(reveal_names=True) is True
    # Even with the gate, a caller that doesn't ask stays redacted.
    assert social_mod.effective_show_names(reveal_names=False) is False


@pytest.mark.asyncio
@respx.mock
async def test_fetch_social_merges_actions_and_joins_names() -> None:
    respx.get(CHAT_URL).mock(return_value=httpx.Response(200, text=_CHAT_CSV))
    respx.get(PLAY_URL).mock(return_value=httpx.Response(200, text=_PLAY_CSV))
    respx.get(LOGIN_URL).mock(return_value=httpx.Response(200, text=_LOGIN_CSV))
    respx.get(REP_URL).mock(return_value=httpx.Response(200, text=_REP_CSV))
    respx.get(CITIZENS_URL).mock(return_value=httpx.Response(200, json=_CITIZENS_JSON))

    surface = await fetch_social(base_url=BASE, api_key="secret", cache_ttl_s=0)
    assert surface.total_chat == 3
    assert surface.per_type_counts == {
        "ChatSent": 3,
        "Play": 2,
        "FirstLogin": 1,
        "ReputationTransfer": 2,
    }
    # Redacted by default (no env gate in this test) — no real names present.
    assert surface.redacted is True
    assert "ekans" not in json.dumps(surface.to_dict())


@pytest.mark.asyncio
@respx.mock
async def test_fetch_social_tolerates_partial_failure() -> None:
    respx.get(CHAT_URL).mock(return_value=httpx.Response(200, text=_CHAT_CSV))
    respx.get(PLAY_URL).mock(return_value=httpx.Response(401))
    respx.get(LOGIN_URL).mock(return_value=httpx.Response(200, text=_LOGIN_CSV))
    respx.get(REP_URL).mock(return_value=httpx.Response(200, text=_REP_CSV))
    respx.get(CITIZENS_URL).mock(return_value=httpx.Response(200, json=_CITIZENS_JSON))

    surface = await fetch_social(base_url=BASE, api_key=None, cache_ttl_s=0)
    assert surface.total_chat == 3  # chat still folded
    assert any("Play" in w and "401" in w for w in surface.warnings)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_social_empty_is_clean() -> None:
    empty_chat = "Citizen,Tag,Message,Count,Time\n"
    respx.get(CHAT_URL).mock(return_value=httpx.Response(200, text=empty_chat))
    respx.get(PLAY_URL).mock(return_value=httpx.Response(200, text="Citizen,Count,Time\n"))
    respx.get(LOGIN_URL).mock(return_value=httpx.Response(200, text="Citizen,Count,Time\n"))
    respx.get(REP_URL).mock(
        return_value=httpx.Response(200, text="Citizen,ReceiverCitizen,Amount,Count,Time\n")
    )

    surface = await fetch_social(base_url=BASE, api_key=None, cache_ttl_s=0)
    assert surface.total_chat == 0
    assert surface.reputation_edges == []
    assert social_template_context(surface)["empty"] is True
    assert "no social activity" in social_markdown(surface).lower()


@pytest.mark.asyncio
@respx.mock
async def test_tool_call_returns_text_blocks_and_fragment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ECO_ADMIN_API_KEY", "k")
    respx.get(CHAT_URL).mock(return_value=httpx.Response(200, text=_CHAT_CSV))
    respx.get(PLAY_URL).mock(return_value=httpx.Response(200, text=_PLAY_CSV))
    respx.get(LOGIN_URL).mock(return_value=httpx.Response(200, text=_LOGIN_CSV))
    respx.get(REP_URL).mock(return_value=httpx.Response(200, text=_REP_CSV))
    respx.get(CITIZENS_URL).mock(return_value=httpx.Response(200, json=_CITIZENS_JSON))

    mcp = build_server()
    handler = mcp.request_handlers[mt.CallToolRequest]
    req = mt.CallToolRequest(
        method="tools/call",
        params=mt.CallToolRequestParams(
            name="get_eco_social",
            arguments={"server": "eco.example.com:3001"},
        ),
    )
    result = await handler(req)
    blocks = result.root.content
    assert len(blocks) == 2
    assert isinstance(blocks[0], mt.TextContent)
    assert "Social" in blocks[0].text
    assert result.root.meta is not None
    assert "Social" in result.root.meta["ui"]["fragment"]
    # Even through the tool, redaction holds by default (no names env gate).
    assert "ekans" not in json.dumps([b.text for b in blocks])


@pytest.mark.asyncio
async def test_list_tools_includes_get_eco_social() -> None:
    mcp = build_server()
    handler = mcp.request_handlers[mt.ListToolsRequest]
    result = await handler(mt.ListToolsRequest(method="tools/list"))
    names = {tool.name for tool in result.root.tools}
    assert "get_eco_social" in names


@respx.mock
def test_preview_social_json_is_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The public /preview/social.json data plane never leaks names — even if an
    operator has lifted the names gate, the SPA path stays redacted."""
    monkeypatch.setenv("ECO_ADMIN_API_KEY", "k")
    monkeypatch.setenv(social_mod.NAMES_ALLOW_ENV, "1")  # gate lifted server-side
    respx.get(CHAT_URL).mock(return_value=httpx.Response(200, text=_CHAT_CSV))
    respx.get(PLAY_URL).mock(return_value=httpx.Response(200, text=_PLAY_CSV))
    respx.get(LOGIN_URL).mock(return_value=httpx.Response(200, text=_LOGIN_CSV))
    respx.get(REP_URL).mock(return_value=httpx.Response(200, text=_REP_CSV))
    respx.get(CITIZENS_URL).mock(return_value=httpx.Response(200, json=_CITIZENS_JSON))

    client = TestClient(create_app())
    resp = client.get("/preview/social.json?server=eco.example.com:3001")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["redacted"] is True
    for real_name in ("coilysiren", "ekans", "redwood"):
        assert real_name not in json.dumps(payload)
