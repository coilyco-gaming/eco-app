"""The shared route registry exposes one contract through REST and MCP."""

from __future__ import annotations

import json
from collections.abc import Callable

import mcp.types as mt
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field

from eco_mcp_app.dual_routes import DualRouteRegistry, DualRouteResult
from eco_mcp_app.http_app import create_app
from eco_mcp_app.server import build_server


class EchoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)
    repeat: int = Field(default=1, ge=1, le=3)


class EchoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    echoed: str
    repeat: int


def _echo_registry(
    on_call: Callable[[EchoRequest], None] | None = None,
) -> DualRouteRegistry:
    registry = DualRouteRegistry()

    @registry.register(
        name="echo_route",
        title="Echo a message",
        description="Repeat one message through the shared route handler.",
        rest_path="/api/echo",
        rest_method="GET",
        input_model=EchoRequest,
        output_model=EchoResponse,
        annotations=mt.ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def echo(request: EchoRequest) -> DualRouteResult[EchoResponse]:
        if on_call is not None:
            on_call(request)
        return DualRouteResult(
            text=f"Echoed {request.repeat} time(s).",
            payload=EchoResponse(
                echoed=request.message * request.repeat,
                repeat=request.repeat,
            ),
        )

    return registry


@pytest.mark.asyncio
async def test_registration_adds_mcp_discovery_and_call() -> None:
    mcp = build_server(_echo_registry())
    list_handler = mcp.request_handlers[mt.ListToolsRequest]
    listed = await list_handler(mt.ListToolsRequest(method="tools/list"))
    tool = next(tool for tool in listed.root.tools if tool.name == "echo_route")

    assert tool.inputSchema["properties"]["repeat"]["type"] == "integer"
    assert tool.outputSchema is not None
    assert tool.outputSchema["properties"]["echoed"]["type"] == "string"
    assert tool.annotations is not None
    assert tool.annotations.readOnlyHint is True

    call_handler = mcp.request_handlers[mt.CallToolRequest]
    called = await call_handler(
        mt.CallToolRequest(
            method="tools/call",
            params=mt.CallToolRequestParams(
                name="echo_route",
                arguments={"message": "hi", "repeat": 2},
            ),
        )
    )

    assert called.root.isError is False
    assert called.root.structuredContent == {"echoed": "hihi", "repeat": 2}
    assert isinstance(called.root.content[0], mt.TextContent)
    assert called.root.content[0].text == "Echoed 2 time(s)."
    assert isinstance(called.root.content[1], mt.TextContent)
    assert json.loads(called.root.content[1].text) == called.root.structuredContent


def test_registration_adds_rest_route_with_shared_coercion() -> None:
    calls: list[EchoRequest] = []
    client = TestClient(create_app(_echo_registry(calls.append)))

    response = client.get("/api/echo", params={"message": "ha", "repeat": "3"})

    assert response.status_code == 200
    assert response.json() == {"echoed": "hahaha", "repeat": 3}
    assert calls == [EchoRequest(message="ha", repeat=3)]


@pytest.mark.asyncio
async def test_invalid_input_never_reaches_shared_handler() -> None:
    calls: list[EchoRequest] = []
    registry = _echo_registry(calls.append)

    rest = TestClient(create_app(registry)).get(
        "/api/echo",
        params={"message": "hi", "repeat": "4"},
    )
    assert rest.status_code == 422
    assert rest.json()["error"] == "invalid_arguments"

    mcp = build_server(registry)
    call_handler = mcp.request_handlers[mt.CallToolRequest]
    called = await call_handler(
        mt.CallToolRequest(
            method="tools/call",
            params=mt.CallToolRequestParams(
                name="echo_route",
                arguments={"message": "hi", "repeat": 4},
            ),
        )
    )
    assert called.root.isError is True
    assert calls == []


def test_registration_rejects_duplicate_surface_keys() -> None:
    registry = _echo_registry()

    with pytest.raises(ValueError, match="duplicate MCP tool name"):
        registry.register(
            name="echo_route",
            title="Duplicate",
            description="Duplicate tool name.",
            rest_path="/api/other",
            rest_method="GET",
            input_model=EchoRequest,
            output_model=EchoResponse,
        )

    with pytest.raises(ValueError, match="duplicate REST route"):
        registry.register(
            name="other_route",
            title="Duplicate",
            description="Duplicate REST route.",
            rest_path="/api/echo",
            rest_method="GET",
            input_model=EchoRequest,
            output_model=EchoResponse,
        )
