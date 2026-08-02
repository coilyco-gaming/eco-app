"""Typed dual registrations for the first public read-only route wave."""

from __future__ import annotations

import json
import math
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, RootModel

from .dual_routes import DualRouteRegistry, DualRouteResult

ToolInvoker = Callable[[str, dict[str, Any]], Awaitable[CallToolResult]]

READ_ONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)
CURATED_SERVERS_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


class EmptyInput(BaseModel):
    """An operation with no inputs."""

    model_config = ConfigDict(extra="forbid")


class ServerInput(BaseModel):
    """Select an Eco server, or use the configured default."""

    model_config = ConfigDict(extra="forbid")

    server: str | None = Field(
        default=None,
        description="Eco server as a host, host:port, or full URL.",
    )


class CurrencyInput(ServerInput):
    """Select an Eco server and optionally one currency."""

    currency: str | None = Field(
        default=None,
        description="Optional case-insensitive currency name.",
    )


class TradeInput(ServerInput):
    """Select an Eco server and optional market filters."""

    item: str | None = Field(
        default=None,
        description="Optional case-insensitive Eco item filter.",
    )
    currency: str | None = Field(
        default=None,
        description="Optional case-insensitive currency name.",
    )


class JsonObjectOutput(RootModel[dict[str, Any]]):
    """A JSON object produced by an established Eco domain report."""


class PublicEcoServer(BaseModel):
    """One curated public Eco server."""

    model_config = ConfigDict(extra="forbid")

    label: str
    host: str
    notes: str


class PublicServersOutput(BaseModel):
    """The curated public Eco server directory."""

    model_config = ConfigDict(extra="forbid")

    servers: list[PublicEcoServer]


PUBLIC_SERVERS_OUTPUT_SCHEMA: dict[str, Any] = PublicServersOutput.model_json_schema()

WAVE1_TOOL_NAMES = frozenset(
    {
        "list_public_eco_servers",
        "get_eco_server_status",
        "get_eco_currency",
        "get_eco_market",
        "get_eco_stores",
        "find_eco_trade",
        "get_eco_civics",
        "get_eco_progression",
        "get_eco_world",
    }
)


def register_wave1_routes(registry: DualRouteRegistry, invoke: ToolInvoker) -> None:
    """Register Wave 1 once, preserving its established names and REST paths."""
    present = {name for name in WAVE1_TOOL_NAMES if registry.has_tool(name)}
    if present:
        if present == WAVE1_TOOL_NAMES:
            return
        names = ", ".join(sorted(present))
        raise ValueError(f"Wave 1 routes partially overlap existing tools: {names}")

    _register_public_servers(registry, invoke)
    _register_json_route(
        registry,
        invoke,
        name="get_eco_server_status",
        title="Eco - server status",
        description=(
            "Show a public Eco server's online players, meteor countdown, world "
            "statistics, economy, and version. Returns a readable summary and "
            "structured JSON. Omit server to use the configured default."
        ),
        rest_path="/preview.json",
        input_model=ServerInput,
    )
    _register_json_route(
        registry,
        invoke,
        name="get_eco_currency",
        title="Eco - currency and money supply",
        description=(
            "Show live Eco currencies, issuance, trade activity, money supply, "
            "and optional per-currency holder detail. Admin-backed data degrades "
            "to the public server headline when the server-side key is absent."
        ),
        rest_path="/preview/currency.json",
        input_model=CurrencyInput,
    )
    _register_json_route(
        registry,
        invoke,
        name="get_eco_market",
        title="Eco - market price intelligence",
        description=(
            "Build per-item market history, volume, and price trends from the "
            "Eco trade ledger. Optional item and currency filters narrow the "
            "report. Requires the server-side admin API key."
        ),
        rest_path="/preview/market.json",
        input_model=TradeInput,
    )
    _register_json_route(
        registry,
        invoke,
        name="get_eco_stores",
        title="Eco - store and trader directory",
        description=(
            "Build store and trader profiles from Eco trade history, including "
            "owners, items, volumes, counterparties, and recent activity. Requires "
            "the server-side admin API key."
        ),
        rest_path="/preview/stores.json",
        input_model=ServerInput,
    )
    _register_json_route(
        registry,
        invoke,
        name="find_eco_trade",
        title="Eco - trade and store logistics",
        description=(
            "Turn trade history and live store shelves into resale, arbitrage, "
            "and supply-gap decisions. Optional item and currency filters narrow "
            "the report. Requires the server-side admin API key."
        ),
        rest_path="/preview/logistics.json",
        input_model=TradeInput,
    )
    _register_json_route(
        registry,
        invoke,
        name="get_eco_civics",
        title="Eco - civics and governance",
        description=(
            "Show election outcomes, turnout, demographic movement, settlements, "
            "and homesteads from Eco's civic history. Requires the server-side "
            "admin API key."
        ),
        rest_path="/preview/civics.json",
        input_model=ServerInput,
    )
    _register_json_route(
        registry,
        invoke,
        name="get_eco_progression",
        title="Eco - progression and skills history",
        description=(
            "Reconstruct server-wide skill trajectories and progression trends "
            "from Eco action exports and daily series. Requires the server-side "
            "admin API key."
        ),
        rest_path="/preview/progression.json",
        input_model=ServerInput,
    )
    _register_json_route(
        registry,
        invoke,
        name="get_eco_world",
        title="Eco - world and industry activity",
        description=(
            "Reconstruct construction, terraforming, roads, pollution, garbage, "
            "and other world activity from Eco's action history. Requires the "
            "server-side admin API key."
        ),
        rest_path="/preview/world.json",
        input_model=ServerInput,
    )


def _register_public_servers(registry: DualRouteRegistry, invoke: ToolInvoker) -> None:
    @registry.register(
        name="list_public_eco_servers",
        title="Eco - list public servers",
        description=(
            "List the curated public Eco servers known to this service. Feed a "
            "returned host into get_eco_server_status to fetch live status."
        ),
        rest_path="/preview/list_public_eco_servers.json",
        rest_method="GET",
        input_model=EmptyInput,
        output_model=PublicServersOutput,
        annotations=CURATED_SERVERS_ANNOTATIONS,
    )
    async def public_servers(request: EmptyInput) -> DualRouteResult[PublicServersOutput]:
        result = await invoke("list_public_eco_servers", request.model_dump())
        text, payload, is_error = _extract_result(result)
        return DualRouteResult(
            text=text,
            payload=PublicServersOutput.model_validate(payload),
            is_error=is_error,
            rest_status=502 if is_error else 200,
        )


def _register_json_route(
    registry: DualRouteRegistry,
    invoke: ToolInvoker,
    *,
    name: str,
    title: str,
    description: str,
    rest_path: str,
    input_model: type[BaseModel],
) -> None:
    decorator = registry.register(
        name=name,
        title=title,
        description=description,
        rest_path=rest_path,
        rest_method="GET",
        input_model=input_model,
        output_model=JsonObjectOutput,
        annotations=READ_ONLY_ANNOTATIONS,
    )

    async def handler(request: BaseModel) -> DualRouteResult[JsonObjectOutput]:
        arguments = request.model_dump(mode="json", exclude_none=True)
        result = await invoke(name, arguments)
        text, payload, is_error = _extract_result(result)
        return DualRouteResult(
            text=text,
            payload=JsonObjectOutput(payload),
            is_error=is_error,
            rest_status=502 if is_error else 200,
        )

    decorator(handler)


def _extract_result(result: CallToolResult) -> tuple[str, dict[str, Any], bool]:
    text_blocks = [block.text for block in result.content if isinstance(block, TextContent)]
    text = text_blocks[0] if text_blocks else "Eco operation completed."
    payload: Any = result.structuredContent
    if not isinstance(payload, dict):
        for block in text_blocks[1:]:
            try:
                candidate = json.loads(block)
            except (TypeError, ValueError):
                continue
            if isinstance(candidate, dict):
                payload = candidate
                break

    is_error = bool(result.isError)
    if not isinstance(payload, dict):
        text = "Eco operation could not produce structured output."
        payload = {
            "view": "error",
            "message": "Structured output was unavailable.",
        }
        is_error = True
    elif is_error and "error" not in payload:
        payload = {
            **payload,
            "error": payload.get("message", "Eco operation failed."),
        }
    return text, _json_safe(payload), is_error


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value
