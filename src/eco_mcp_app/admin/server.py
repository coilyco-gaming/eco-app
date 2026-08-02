"""The privileged, read-only inside-out Eco MCP mounted at ``/admin``."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from mcp.server.lowlevel import Server
from mcp.types import CallToolResult, TextContent, Tool

from .rcon import PUBLIC_DENY, EcoRconClient, RconError, RconQuery, coerce_query
from .redaction import (
    DEFAULT_LEVEL,
    RedactionLevel,
    coerce_level,
    hash_name,
    raw_allowed,
    redact_config,
    redact_text,
)
from .runtime import EcoRuntimeClient
from .state import (
    CONFIG_DIFFS,
    KNOWN_CONFIGS,
    LOG_STREAMS,
    MAX_EVENT_LIMIT,
    MAX_LOG_LINES,
    MAX_LOG_MATCHES,
    StateStore,
)

_LEVEL_PROP = {
    "type": "string",
    "enum": [level.value for level in RedactionLevel],
    "description": (
        "Redaction level. `public` hashes structured names and strips secrets, "
        "`operator` (default) shows names and strips secrets, and `raw` is denied "
        "unless ECO_ADMIN_ALLOW_RAW is explicitly set."
    ),
}
_NO_PATHS = "This tool uses a server-owned enum and never accepts a filesystem path."


def _error(message: str) -> CallToolResult:
    payload = {"view": "error", "message": message}
    return CallToolResult(
        content=[
            TextContent(type="text", text=f"**Error:** {message}"),
            TextContent(type="text", text=json.dumps(payload)),
        ],
        isError=True,
    )


def _ok(title: str, payload: dict[str, Any]) -> CallToolResult:
    markdown = f"**{title}**\n\n```json\n{json.dumps(payload, indent=2, sort_keys=True)}\n```"
    return CallToolResult(
        content=[
            TextContent(type="text", text=markdown),
            TextContent(type="text", text=json.dumps(payload)),
        ],
    )


def _gate_level(raw_arg: Any) -> tuple[RedactionLevel | None, CallToolResult | None]:
    try:
        level = coerce_level(raw_arg)
    except ValueError as exc:
        return None, _error(str(exc))
    if level is RedactionLevel.RAW and not raw_allowed():
        return None, _error(
            "raw level denied: secrets are default-DENY. Set ECO_ADMIN_ALLOW_RAW to permit it."
        )
    return level, None


def _operator_only(level: RedactionLevel, surface: str) -> CallToolResult | None:
    if level is RedactionLevel.PUBLIC:
        return _error(
            f"{surface} is operator-only because unstructured text cannot guarantee name redaction."
        )
    return None


def _hash_backup_label(
    entry: dict[str, Any] | None, level: RedactionLevel
) -> dict[str, Any] | None:
    if entry is None or level is not RedactionLevel.PUBLIC:
        return entry
    out = dict(entry)
    label = out.get("label")
    if isinstance(label, str) and label:
        out["label"] = hash_name(label)
        parent = str(out.get("path", "")).rsplit("/", 1)[0]
        out["path"] = f"{parent}/{out['label']}".lstrip("/")
    return out


def _state_call(
    title: str,
    operation: Callable[[], dict[str, Any]],
    level: RedactionLevel,
    *,
    structured_redaction: bool = True,
) -> CallToolResult:
    try:
        payload = operation()
    except (KeyError, RuntimeError, ValueError, OSError) as exc:
        return _error(str(exc))
    if structured_redaction:
        payload = redact_config(payload, level)
    payload["level"] = level.value
    return _ok(title, payload)


def _tool(
    name: str,
    title: str,
    description: str,
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> Tool:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {"level": _LEVEL_PROP, **(properties or {})},
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return Tool(name=name, title=title, description=description, inputSchema=schema)


def build_admin_server(
    store: StateStore | None = None,
    *,
    rcon: EcoRconClient | None = None,
    runtime: EcoRuntimeClient | None = None,
) -> Server:
    """Construct the feature-flagged privileged MCP.

    The three dependencies are injectable for deterministic tests. Production
    values resolve lazily from environment variables when a tool is called.
    """
    server: Server = Server("eco-mcp-admin")
    rcon_client = rcon
    runtime_client = runtime

    def _store() -> StateStore:
        return store if store is not None else StateStore.from_env()

    def _rcon() -> EcoRconClient:
        nonlocal rcon_client
        if rcon_client is None:
            rcon_client = EcoRconClient()
        return rcon_client

    def _runtime() -> EcoRuntimeClient:
        nonlocal runtime_client
        if runtime_client is None:
            runtime_client = EcoRuntimeClient()
        return runtime_client

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            _tool(
                "eco_admin_save_status",
                "Eco admin - save status",
                "Size and age of fixed world save files under the read-only Storage mount.",
            ),
            _tool(
                "eco_admin_backup_list",
                "Eco admin - backup list",
                "Count, cadence, and newest/oldest fixed world backups.",
            ),
            _tool(
                "eco_admin_world_meta",
                "Eco admin - world metadata",
                "Selected non-secret world generator metadata from Configs/WorldGenerator.eco.",
            ),
            _tool(
                "eco_admin_config_get",
                "Eco admin - read config",
                f"Read one known Eco config. {_NO_PATHS}",
                {
                    "name": {
                        "type": "string",
                        "enum": sorted(KNOWN_CONFIGS),
                        "description": "Known config name.",
                    }
                },
                ["name"],
            ),
            _tool(
                "eco_admin_config_diff",
                "Eco admin - config diff",
                f"Read the fixed current and diff files for one known config. {_NO_PATHS}",
                {
                    "name": {
                        "type": "string",
                        "enum": sorted(CONFIG_DIFFS),
                        "description": "Known diff name.",
                    }
                },
                ["name"],
            ),
            _tool(
                "eco_admin_mod_configs",
                "Eco admin - mod configs",
                (
                    "Read the fixed DiscordLink, MightyMoose, NidToolbox, "
                    "and StrangeWorlds config set."
                ),
            ),
            _tool(
                "eco_admin_events_recent",
                "Eco admin - recent Chronicler events",
                "Read recent events from fixed EcoReplay SQLite or JSONL storage.",
                {
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_EVENT_LIMIT,
                        "default": 50,
                    }
                },
            ),
            _tool(
                "eco_admin_player_activity",
                "Eco admin - player activity",
                "Aggregate the bounded recent Chronicler event sample by citizen and action.",
                {
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_EVENT_LIMIT,
                        "default": MAX_EVENT_LIMIT,
                    }
                },
            ),
            _tool(
                "eco_admin_log_tail",
                "Eco admin - log tail",
                f"Tail the newest file in one fixed subsystem log stream. {_NO_PATHS}",
                {
                    "stream": {"type": "string", "enum": sorted(LOG_STREAMS)},
                    "lines": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_LOG_LINES,
                        "default": 100,
                    },
                },
                ["stream"],
            ),
            _tool(
                "eco_admin_log_grep",
                "Eco admin - literal log search",
                (
                    "Search one fixed subsystem stream with a bounded, case-insensitive literal. "
                    "Regex and paths are not accepted."
                ),
                {
                    "stream": {"type": "string", "enum": sorted(LOG_STREAMS)},
                    "query": {"type": "string", "minLength": 1, "maxLength": 120},
                    "matches": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_LOG_MATCHES,
                        "default": 50,
                    },
                },
                ["stream", "query"],
            ),
            _tool(
                "eco_admin_mods_installed",
                "Eco admin - installed mods",
                "Inventory fixed Mods/UserCode directories and compare configured mod names.",
            ),
            _tool(
                "eco_admin_live_status",
                "Eco admin - live Eco status",
                (
                    "Read the node-local Eco HTTP /info route with a fixed timeout "
                    "and response budget."
                ),
            ),
            _tool(
                "eco_admin_service_health",
                "Eco admin - service health",
                (
                    "Report node-local Eco /info reachability. This does not execute systemctl "
                    "or enter a workload."
                ),
            ),
            _tool(
                "eco_admin_rcon_query",
                "Eco admin - read-only RCON query",
                (
                    "Run one server-owned read-only RCON command. The caller chooses an enum only. "
                    "Free-form and mutating commands are impossible through this tool."
                ),
                {
                    "query": {
                        "type": "string",
                        "enum": [item.value for item in RconQuery],
                    }
                },
                ["query"],
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
        args = arguments or {}
        level, error = _gate_level(args.get("level"))
        if error is not None:
            return error
        assert level is not None

        if name == "eco_admin_save_status":
            try:
                payload = _store().save_status()
            except (RuntimeError, OSError) as exc:
                return _error(str(exc))
            payload["level"] = level.value
            return _ok("Eco save status", payload)
        if name == "eco_admin_backup_list":
            try:
                payload = _store().backup_list()
            except (RuntimeError, OSError) as exc:
                return _error(str(exc))
            payload["newest"] = _hash_backup_label(payload.get("newest"), level)
            payload["oldest"] = _hash_backup_label(payload.get("oldest"), level)
            payload["backups"] = [
                _hash_backup_label(item, level) for item in payload.get("backups", [])
            ]
            payload["level"] = level.value
            return _ok("Eco backups", payload)
        if name == "eco_admin_world_meta":
            return _state_call("Eco world metadata", _store().world_meta, level)
        if name == "eco_admin_config_get":
            config_name = args.get("name")
            if not isinstance(config_name, str):
                return _error("`name` is required and must be a known config.")
            return _state_call(
                f"Eco config {config_name}",
                lambda: _store().read_config(config_name),
                level,
            )
        if name == "eco_admin_config_diff":
            diff_name = args.get("name")
            if not isinstance(diff_name, str):
                return _error("`name` is required and must be a known config diff.")
            return _state_call(
                f"Eco config diff {diff_name}",
                lambda: _store().config_diff(diff_name),
                level,
            )
        if name == "eco_admin_mod_configs":
            return _state_call("Eco mod configs", _store().mod_configs, level)
        if name == "eco_admin_events_recent":
            limit = args.get("limit", 50)
            return _state_call(
                "Recent Eco events",
                lambda: _store().events_recent(limit),
                level,
            )
        if name == "eco_admin_player_activity":
            limit = args.get("limit", MAX_EVENT_LIMIT)
            return _state_call(
                "Eco player activity",
                lambda: _store().player_activity(limit),
                level,
            )
        if name == "eco_admin_log_tail":
            operator_error = _operator_only(level, "log reads")
            if operator_error is not None:
                return operator_error
            stream = args.get("stream")
            if not isinstance(stream, str):
                return _error("`stream` is required and must be a known log stream.")
            try:
                payload = _store().log_tail(stream, args.get("lines", 100))
            except (KeyError, RuntimeError, ValueError, OSError) as exc:
                return _error(str(exc))
            payload["lines"] = [redact_text(str(line), level) for line in payload["lines"]]
            payload["level"] = level.value
            return _ok("Eco log tail", payload)
        if name == "eco_admin_log_grep":
            operator_error = _operator_only(level, "log reads")
            if operator_error is not None:
                return operator_error
            stream = args.get("stream")
            query = args.get("query")
            if not isinstance(stream, str) or not isinstance(query, str):
                return _error("`stream` and literal `query` are required.")
            try:
                payload = _store().log_grep(stream, query, args.get("matches", 50))
            except (KeyError, RuntimeError, ValueError, OSError) as exc:
                return _error(str(exc))
            for match in payload["matches"]:
                match["text"] = redact_text(str(match["text"]), level)
            payload["level"] = level.value
            return _ok("Eco log search", payload)
        if name == "eco_admin_mods_installed":
            return _state_call("Installed Eco mods", _store().mods_installed, level)
        if name == "eco_admin_live_status":
            try:
                payload = await _runtime().live_status()
            except (RuntimeError, ValueError, OSError) as exc:
                return _error(str(exc))
            payload = redact_config(payload, level)
            payload["level"] = level.value
            return _ok("Live Eco status", payload)
        if name == "eco_admin_service_health":
            try:
                payload = await _runtime().service_health()
            except (RuntimeError, ValueError, OSError) as exc:
                return _error(str(exc))
            payload["level"] = level.value
            return _ok("Eco service health", payload)
        if name == "eco_admin_rcon_query":
            try:
                query = coerce_query(args.get("query"))
            except ValueError as exc:
                return _error(str(exc))
            if level is RedactionLevel.PUBLIC and query in PUBLIC_DENY:
                return _error(
                    f"RCON query {query.value!r} is operator-only because it names people."
                )
            try:
                payload = await _rcon().query(query)
            except (RconError, RuntimeError, ValueError, OSError) as exc:
                return _error(str(exc))
            payload["response"] = redact_text(str(payload["response"]), level)
            payload["level"] = level.value
            return _ok("Eco RCON query", payload)
        return _error(f"unknown tool {name!r}")

    return server


__all__ = ["DEFAULT_LEVEL", "build_admin_server"]
