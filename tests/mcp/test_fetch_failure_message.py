"""Unreachable-server errors name a cause and a URL (eco-app#228).

`get_server_status(server="eco.bleedcraft.com:3001")` returned
`"Could not reach Eco server: "` — nothing after the colon. httpx's
connect-side exceptions frequently carry an empty `str()`, so interpolating
the exception alone told an operator nothing: down host, wrong port, blocked,
or timed out all rendered identically.
"""

from __future__ import annotations

import json

import httpx
import mcp.types as mt
import pytest
import respx

from eco_mcp_app import server as eco_server
from eco_mcp_app.server import DEFAULT_ECO_INFO_URL, _fetch_failure, build_server


@pytest.fixture(autouse=True)
def _clear_info_cache() -> None:
    eco_server._info_cache.clear()


def test_empty_exception_text_still_names_the_type() -> None:
    request = httpx.Request("GET", "http://eco.bleedcraft.com:3001/info")
    failure = _fetch_failure(httpx.ConnectTimeout("", request=request))
    assert "ConnectTimeout" in failure
    assert "http://eco.bleedcraft.com:3001/info" in failure
    assert not failure.endswith(": ")


def test_detail_is_kept_when_the_exception_has_one() -> None:
    request = httpx.Request("GET", "http://eco.example.com:3001/info")
    failure = _fetch_failure(httpx.ConnectError("[Errno 61] Connection refused", request=request))
    assert "ConnectError" in failure
    assert "[Errno 61] Connection refused" in failure
    assert "http://eco.example.com:3001/info" in failure


def test_status_errors_name_the_status_code() -> None:
    request = httpx.Request("GET", "http://eco.example.com:3001/info")
    response = httpx.Response(503, request=request)
    failure = _fetch_failure(
        httpx.HTTPStatusError("server error", request=request, response=response)
    )
    assert "HTTP 503" in failure


def test_request_less_exception_degrades_to_the_type() -> None:
    # httpx raises RuntimeError from `.request` when the transport never set
    # it; the message must still say something.
    failure = _fetch_failure(httpx.ConnectTimeout(""))
    assert failure == "ConnectTimeout"


@pytest.mark.asyncio
@respx.mock
async def test_tool_error_payload_carries_the_cause() -> None:
    respx.get(DEFAULT_ECO_INFO_URL).mock(side_effect=httpx.ConnectTimeout(""))
    mcp = build_server()
    handler = mcp.request_handlers[mt.CallToolRequest]
    result = await handler(
        mt.CallToolRequest(
            method="tools/call",
            params=mt.CallToolRequestParams(name="get_server_status", arguments={}),
        )
    )
    payload = json.loads(result.root.content[1].text)
    assert payload["view"] == "error"
    assert not payload["message"].endswith(": ")
    assert "ConnectTimeout" in payload["message"]
