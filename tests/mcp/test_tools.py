"""Exercise the tool surface end-to-end through the MCP server."""

from __future__ import annotations

import json

import mcp.types as mt
import pytest

from eco_mcp_app.server import KNOWN_PUBLIC_SERVERS, PUBLIC_SERVERS_OUTPUT_SCHEMA, build_server


@pytest.mark.asyncio
async def test_list_tools_advertises_all_tools() -> None:
    mcp = build_server()
    handler = mcp.request_handlers[mt.ListToolsRequest]
    result = await handler(mt.ListToolsRequest(method="tools/list"))
    names = {tool.name for tool in result.root.tools}
    assert names == {
        "get_server_status",
        "list_public_servers",
        "get_economy",
        "get_map",
        "get_milestones",
        "get_species",
        "explain_item",
        "get_crafting_atlas",
        "get_world",
        "get_trades",
        "get_market",
        "get_stores",
        "get_progression",
        "get_social",
        "find_trade",
        "fair_price",
        "get_government",
        "get_civics",
        "get_region",
        "get_climate",
        "get_currency",
        "trade_watchers",
    }


@pytest.mark.asyncio
async def test_list_public_servers_returns_curated_list() -> None:
    mcp = build_server()
    handler = mcp.request_handlers[mt.CallToolRequest]
    req = mt.CallToolRequest(
        method="tools/call",
        params=mt.CallToolRequestParams(name="list_public_servers", arguments={}),
    )
    result = await handler(req)
    assert result.root.structuredContent == {"servers": KNOWN_PUBLIC_SERVERS}
    blocks = result.root.content
    assert len(blocks) == 2
    # Both blocks are TextContent by construction; narrow for mypy.
    assert isinstance(blocks[0], mt.TextContent)
    assert isinstance(blocks[1], mt.TextContent)
    md = blocks[0].text
    payload = json.loads(blocks[1].text)
    assert payload["servers"] == KNOWN_PUBLIC_SERVERS
    for s in KNOWN_PUBLIC_SERVERS:
        assert s["label"] in md
        assert s["host"] in md


@pytest.mark.asyncio
async def test_list_public_servers_advertises_safe_structured_metadata() -> None:
    mcp = build_server()
    handler = mcp.request_handlers[mt.ListToolsRequest]
    result = await handler(mt.ListToolsRequest(method="tools/list"))
    tool = next(tool for tool in result.root.tools if tool.name == "list_public_servers")

    assert tool.annotations is not None
    assert tool.annotations.readOnlyHint is True
    assert tool.annotations.destructiveHint is False
    assert tool.annotations.idempotentHint is True
    assert tool.annotations.openWorldHint is False
    assert tool.outputSchema == PUBLIC_SERVERS_OUTPUT_SCHEMA
