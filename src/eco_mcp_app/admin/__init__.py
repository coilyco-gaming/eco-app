"""Privileged, read-only inside-out MCP for Eco server administration.

Distinct from the public outside-in MCP in ``eco_mcp_app.server`` (which reads
a live server's public HTTP surfaces). This one reads fixed read-only
Storage/Configs/Logs/Mods mounts, node-local ``/info``, and twelve enum-only
RCON queries. It is mounted at ``/admin`` only when ``ECO_ADMIN_ENABLED`` is
set. The public app deployment leaves that flag off.

Three redaction levels gate disclosure (see ``redaction``); file access is by
fixed enum, never a caller-supplied path (see ``state``).
"""

from __future__ import annotations

from .rcon import RCON_COMMANDS, EcoRconClient, RconQuery
from .redaction import DEFAULT_LEVEL, RedactionLevel, raw_allowed, redact_config
from .runtime import EcoRuntimeClient
from .server import build_admin_server
from .state import CONFIG_DIFFS, KNOWN_CONFIGS, LOG_STREAMS, MOD_CONFIGS, StateStore

__all__ = [
    "CONFIG_DIFFS",
    "DEFAULT_LEVEL",
    "KNOWN_CONFIGS",
    "LOG_STREAMS",
    "MOD_CONFIGS",
    "RCON_COMMANDS",
    "EcoRconClient",
    "EcoRuntimeClient",
    "RconQuery",
    "RedactionLevel",
    "StateStore",
    "build_admin_server",
    "raw_allowed",
    "redact_config",
]
