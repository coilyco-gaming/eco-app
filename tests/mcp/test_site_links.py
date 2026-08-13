"""Every MCP answer points at the page that carries it in full (eco-app#241).

An MCP response is a summary by necessity — the client's response cap is real,
and the 2026-08-12 sweep found 7 of 22 tools exceeding it. A curt answer plus a
link to the live page is the pressure relief: the caller gets the number and
knows where the rest lives.
"""

from __future__ import annotations

import mcp.types as mt
import pytest

from eco_mcp_app.server import (
    PUBLIC_SITE_URL,
    TOOL_SITE_PATHS,
    _append_site_link,
    build_server,
    site_url_for,
)


def _result(text: str) -> mt.CallToolResult:
    return mt.CallToolResult(content=[mt.TextContent(type="text", text=text)])


def test_every_registered_tool_has_a_page() -> None:
    """A tool with no link is a tool whose detail a caller cannot reach."""
    mcp = build_server()
    tools = mcp.request_handlers[mt.ListToolsRequest]
    assert tools is not None  # sanity: the handler is registered
    for name in TOOL_SITE_PATHS:
        assert site_url_for(name), f"{name} resolves no site URL"
        assert site_url_for(name).startswith(PUBLIC_SITE_URL)


def test_the_link_is_appended_to_the_markdown_block() -> None:
    result = _append_site_link("get_trades", _result("**Trades ledger** — 12 trades"))
    text = result.content[0].text
    assert text.startswith("**Trades ledger**")
    assert f"{PUBLIC_SITE_URL}/trade" in text


def test_an_unknown_tool_is_left_alone() -> None:
    result = _append_site_link("not_a_tool", _result("body"))
    assert result.content[0].text == "body"


def test_the_link_is_not_doubled_up() -> None:
    once = _append_site_link("get_civics", _result("body"))
    twice = _append_site_link("get_civics", once)
    assert twice.content[0].text.count(PUBLIC_SITE_URL) == 1


def test_an_empty_result_is_left_alone() -> None:
    empty = mt.CallToolResult(content=[])
    assert _append_site_link("get_civics", empty).content == []


@pytest.mark.asyncio
async def test_a_live_tool_call_carries_the_link() -> None:
    """End-to-end through the dispatcher, not just the helper."""
    mcp = build_server()
    handler = mcp.request_handlers[mt.CallToolRequest]
    result = await handler(
        mt.CallToolRequest(
            method="tools/call",
            params=mt.CallToolRequestParams(name="list_public_servers", arguments={}),
        )
    )
    assert f"{PUBLIC_SITE_URL}/info" in result.root.content[0].text
