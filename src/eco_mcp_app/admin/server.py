"""The privileged /admin MCP server: three read-only on-disk state tools.

Built as a second ``mcp.server.lowlevel.Server`` distinct from the public
outside-in server in ``eco_mcp_app.server``. Mounted at ``/admin`` by
``http_app`` only when ``ECO_ADMIN_ENABLED`` is set. Every tool is read-only,
takes a redaction ``level`` (default ``operator``), and reaches files by fixed
enum, never a caller-supplied path.

Each tool returns a markdown summary block plus a JSON block, matching the
shape of the public server's tool results.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.lowlevel import Server
from mcp.types import CallToolResult, TextContent, Tool

from .redaction import (
    DEFAULT_LEVEL,
    RedactionLevel,
    coerce_level,
    hash_name,
    raw_allowed,
    redact_config,
)
from .state import KNOWN_CONFIGS, StateStore

_LEVEL_PROP = {
    "type": "string",
    "enum": [level.value for level in RedactionLevel],
    "description": (
        "Redaction level. `public` hashes names and strips secrets, `operator` "
        "(default) shows names and strips secrets, `raw` also discloses secrets "
        "but is DENIED unless ECO_ADMIN_ALLOW_RAW is set."
    ),
}


def _error(message: str) -> CallToolResult:
    payload = {"view": "error", "message": message}
    return CallToolResult(
        content=[
            TextContent(type="text", text=f"**Error:** {message}"),
            TextContent(type="text", text=json.dumps(payload)),
        ],
        isError=True,
    )


def _ok(markdown: str, payload: dict[str, Any]) -> CallToolResult:
    return CallToolResult(
        content=[
            TextContent(type="text", text=markdown),
            TextContent(type="text", text=json.dumps(payload)),
        ],
    )


def _gate_level(raw_arg: Any) -> tuple[RedactionLevel | None, CallToolResult | None]:
    """Resolve the requested level and enforce the raw-level DENY.

    Returns ``(level, None)`` on success or ``(None, error_result)`` when the
    level is unknown or raw is requested without ``ECO_ADMIN_ALLOW_RAW``.
    """
    try:
        level = coerce_level(raw_arg)
    except ValueError as exc:
        return None, _error(str(exc))
    if level is RedactionLevel.RAW and not raw_allowed():
        return None, _error(
            "raw level denied: secrets are default-DENY. Set ECO_ADMIN_ALLOW_RAW to permit "
            "disclosing tokens and passwords."
        )
    return level, None


def _hash_backup_label(
    entry: dict[str, Any] | None, level: RedactionLevel
) -> dict[str, Any] | None:
    """Hash a backup filename at the public level (it can embed a world name)."""
    if entry is None or level is not RedactionLevel.PUBLIC:
        return entry
    out = dict(entry)
    label = out.get("label")
    if isinstance(label, str) and label:
        out["label"] = hash_name(label)
        out["path"] = f"{out.get('path', '').rsplit('/', 1)[0]}/{out['label']}".lstrip("/")
    return out


def build_admin_server(store: StateStore | None = None) -> Server:
    """Construct the privileged /admin MCP Server.

    ``store`` is injected in tests. In the running service it is resolved from
    ``ECO_STATE_DIR`` lazily per call, so importing this module with the flag on
    but no state dir configured fails at call time with a clear message rather
    than at construction.
    """
    server: Server = Server("eco-mcp-admin")

    def _store() -> StateStore:
        return store if store is not None else StateStore.from_env()

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="eco_save_status",
                title="Eco admin - save status",
                description=(
                    "Size and age of the on-disk world save files (Game.eco, Game.db) "
                    "in the local Eco state checkout. Read-only, local files only."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {"level": _LEVEL_PROP},
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="eco_backup_list",
                title="Eco admin - backup list",
                description=(
                    "Count, cadence (median gap), and newest/oldest of the rotated "
                    "world backups in the local Eco state checkout. Read-only."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {"level": _LEVEL_PROP},
                    "additionalProperties": False,
                },
            ),
            Tool(
                name="eco_config_get",
                title="Eco admin - read a named config",
                description=(
                    "Read one named Eco server config (a `.eco` or `.diff.json` file) "
                    "from the local state checkout, redacted per `level`. The config "
                    "is chosen from a fixed enum of known names - arbitrary filesystem "
                    "paths are rejected. Secrets are stripped unless `level` is `raw` "
                    "AND ECO_ADMIN_ALLOW_RAW is set."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "enum": sorted(KNOWN_CONFIGS),
                            "description": "Which known config to read (enum-only, no paths).",
                        },
                        "level": _LEVEL_PROP,
                    },
                    "required": ["name"],
                    "additionalProperties": False,
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
        args = arguments or {}
        level, err = _gate_level(args.get("level"))
        if err is not None:
            return err
        assert level is not None  # narrowed by err-None branch

        if name == "eco_save_status":
            return _save_status(_store(), level)
        if name == "eco_backup_list":
            return _backup_list(_store(), level)
        if name == "eco_config_get":
            return _config_get(_store(), level, args.get("name"))
        return _error(f"unknown tool {name!r}")

    return server


def _fmt_size(size: int | None) -> str:
    if size is None:
        return "-"
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def _fmt_age(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    if seconds < 90:
        return f"{seconds:.0f}s"
    if seconds < 5400:
        return f"{seconds / 60:.0f}m"
    if seconds < 172800:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def _save_status(store: StateStore, level: RedactionLevel) -> CallToolResult:
    try:
        payload = store.save_status()
    except RuntimeError as exc:
        return _error(str(exc))
    payload["level"] = level.value
    lines = [f"**Eco save status** - level `{level.value}`"]
    for f in payload["files"]:
        if f["present"]:
            lines.append(
                f"- {f['label']}: {_fmt_size(f['sizeBytes'])}, "
                f"modified {f['modifiedISO']} (age {_fmt_age(f['ageSeconds'])})"
            )
        else:
            lines.append(f"- {f['label']}: not present")
    return _ok("\n".join(lines), payload)


def _backup_list(store: StateStore, level: RedactionLevel) -> CallToolResult:
    try:
        payload = store.backup_list()
    except RuntimeError as exc:
        return _error(str(exc))
    payload["level"] = level.value
    payload["newest"] = _hash_backup_label(payload.get("newest"), level)
    payload["oldest"] = _hash_backup_label(payload.get("oldest"), level)
    payload["backups"] = [_hash_backup_label(b, level) for b in payload.get("backups", [])]
    cadence = payload.get("cadenceSeconds")
    lines = [
        f"**Eco backups** - level `{level.value}`",
        f"- count: {payload['count']}",
        f"- cadence: {'~' + _fmt_age(cadence) if cadence is not None else 'n/a'}",
    ]
    newest, oldest = payload.get("newest"), payload.get("oldest")
    if newest:
        lines.append(f"- newest: {newest['label']} at {newest['modifiedISO']}")
    if oldest:
        lines.append(f"- oldest: {oldest['label']} at {oldest['modifiedISO']}")
    return _ok("\n".join(lines), payload)


def _config_get(store: StateStore, level: RedactionLevel, name: Any) -> CallToolResult:
    if not name or not isinstance(name, str):
        return _error("`name` is required and must be one of the known configs.")
    try:
        result = store.read_config(name)
    except KeyError as exc:
        return _error(str(exc))
    except RuntimeError as exc:
        return _error(str(exc))
    result["level"] = level.value
    if not result.get("present"):
        md = f"**Eco config `{name}`** ({result['path']}) - not present in the state checkout."
        return _ok(md, result)
    if "content" in result:
        result["content"] = redact_config(result["content"], level)
    body = json.dumps(result.get("content"), indent=2, sort_keys=True)
    md = (
        f"**Eco config `{name}`** ({result['path']}) - level `{level.value}`\n\n"
        f"```json\n{body}\n```"
    )
    return _ok(md, result)


__all__ = ["DEFAULT_LEVEL", "build_admin_server"]
