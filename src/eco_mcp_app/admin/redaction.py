"""Redaction levels for the privileged /admin MCP.

Three levels gate how much of an on-disk Eco config a tool discloses:

- ``public``   - names (players, admins, server, Discord) are hashed, secrets
                 stripped. Safe to paste into a public channel.
- ``operator`` - names shown in the clear, secrets still stripped. The default.
- ``raw``      - operator plus the secrets themselves. DEFAULT DENY: a raw
                 request is refused unless ``ECO_ADMIN_ALLOW_RAW`` is set, so no
                 ordinary call can ever surface a Discord bot token or a
                 server-api-token.

Redaction walks a parsed config tree and decides per scalar from the *key* it
sits under. Secret keys win over name keys, so ``DiscordToken`` (which matches
both) is treated as a secret, never merely hashed.
"""

from __future__ import annotations

import hashlib
import os
import re
from enum import StrEnum
from typing import Any


class RedactionLevel(StrEnum):
    """How much on-disk state a tool call may disclose."""

    PUBLIC = "public"
    OPERATOR = "operator"
    RAW = "raw"


DEFAULT_LEVEL = RedactionLevel.OPERATOR

# Env flag that lifts the raw-level DENY. Absent/false -> raw is refused.
RAW_ALLOW_ENV = "ECO_ADMIN_ALLOW_RAW"

# Sentinel a stripped secret is replaced with. ASCII on purpose (public-safe,
# grep-friendly, no encoding surprises in a chat host).
SECRET_SENTINEL = "[redacted-secret]"

# Keys whose *value* is a secret: any Configs token, plus password/secret/key
# material. Matched case-insensitively against the key name. These never leave
# the process above ``raw``.
_SECRET_KEY = re.compile(r"token|secret|password|passwd|api[_-]?key|apikey|credential", re.I)

# Keys whose value identifies a person or a server - hashed at ``public``,
# shown from ``operator`` up. Deliberately broad: over-hashing at the public
# level is harmless, under-hashing leaks identity.
_NAME_KEY = re.compile(
    r"name|description|discord|admin|whitelist|blacklist|user|owner|player|email|address|steam",
    re.I,
)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def raw_allowed() -> bool:
    """True when the operator has explicitly opted into raw (secret) disclosure."""
    return _truthy(os.environ.get(RAW_ALLOW_ENV))


def coerce_level(value: str | RedactionLevel | None) -> RedactionLevel:
    """Parse a caller-supplied level, defaulting to ``operator``.

    Raises ``ValueError`` on an unknown level so the tool can surface a clean
    error rather than silently widening or narrowing disclosure.
    """
    if value is None or value == "":
        return DEFAULT_LEVEL
    if isinstance(value, RedactionLevel):
        return value
    try:
        return RedactionLevel(str(value).strip().lower())
    except ValueError as exc:
        allowed = ", ".join(level.value for level in RedactionLevel)
        raise ValueError(f"unknown redaction level {value!r}; expected one of: {allowed}") from exc


def hash_name(value: str) -> str:
    """Stable, non-reversible tag for a name at the ``public`` level.

    Same input -> same tag within a run, so two hashed references to one player
    stay correlatable without disclosing who they are.
    """
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"[hashed:{digest}]"


def _is_secret_key(key: str) -> bool:
    return bool(_SECRET_KEY.search(key))


def _is_name_key(key: str) -> bool:
    return bool(_NAME_KEY.search(key))


def redact_config(data: Any, level: RedactionLevel, *, _key: str = "") -> Any:
    """Return a redacted copy of a parsed config tree for the given level.

    ``_key`` carries the name of the dict key a scalar sits under so leaf
    handling can classify it. Lists inherit their parent key, so an array of
    whitelist names is hashed element-wise at ``public``.
    """
    if isinstance(data, dict):
        return {k: redact_config(v, level, _key=str(k)) for k, v in data.items()}
    if isinstance(data, list):
        return [redact_config(item, level, _key=_key) for item in data]

    # Leaf. Secret classification wins over name classification: a key that is
    # both (e.g. DiscordToken) must never be merely hashed.
    if _is_secret_key(_key):
        return data if level is RedactionLevel.RAW else SECRET_SENTINEL
    if _is_name_key(_key) and isinstance(data, str) and data:
        return hash_name(data) if level is RedactionLevel.PUBLIC else data
    return data
