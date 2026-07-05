"""Privileged, inside-out MCP for on-disk Eco server state.

Distinct from the public outside-in MCP in ``eco_mcp_app.server`` (which reads
a live server's HTTP ``/info``). This one reads a *local checkout* of the
server's Storage/Configs tree and is mounted at ``/admin``, feature-flagged
behind ``ECO_ADMIN_ENABLED`` (default off) so the public deploy never exposes
it. Phase 1 of the Eco MCP battery (coilyco-gaming/eco-app#42): read-only,
local files, no live-server touch, no deploy.

Three redaction levels gate disclosure (see ``redaction``); file access is by
fixed enum, never a caller-supplied path (see ``state``).
"""

from __future__ import annotations

from .redaction import DEFAULT_LEVEL, RedactionLevel, raw_allowed, redact_config
from .server import build_admin_server
from .state import KNOWN_CONFIGS, StateStore

__all__ = [
    "DEFAULT_LEVEL",
    "KNOWN_CONFIGS",
    "RedactionLevel",
    "StateStore",
    "build_admin_server",
    "raw_allowed",
    "redact_config",
]
