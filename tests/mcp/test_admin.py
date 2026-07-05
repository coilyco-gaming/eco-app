"""Tests for the privileged /admin MCP (phase 1 of the Eco MCP battery).

Everything runs against a local sample state checkout copied from
``tests/mcp/fixtures/eco_state`` into ``tmp_path`` with deterministic mtimes,
so save ages and backup cadence are stable. No live server is touched.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import mcp.types as mt
import pytest

from eco_mcp_app.admin import RedactionLevel, StateStore, build_admin_server
from eco_mcp_app.admin.redaction import (
    SECRET_SENTINEL,
    coerce_level,
    hash_name,
    raw_allowed,
    redact_config,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "eco_state"

# Fixed clock for age/cadence math. Backups sit at NOW-9000/-7200/-5400 (an
# even 1800s cadence), the saves more recently.
NOW = 1_720_000_000.0


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    """A writable copy of the sample state tree with controlled mtimes."""
    root = tmp_path / "eco_state"
    shutil.copytree(FIXTURE_ROOT, root)
    os.utime(root / "Storage" / "Game.eco", (NOW - 3600, NOW - 3600))
    os.utime(root / "Storage" / "Game.db", (NOW - 1800, NOW - 1800))
    backups = {
        "backup-2026-07-05-0100.eco": NOW - 9000,
        "backup-2026-07-05-0130.eco": NOW - 7200,
        "backup-2026-07-05-0200.eco": NOW - 5400,
    }
    for name, mtime in backups.items():
        os.utime(root / "Storage" / "Backup" / name, (mtime, mtime))
    return root


# --------------------------------------------------------------------------- #
# Redaction unit tests                                                         #
# --------------------------------------------------------------------------- #


def test_redact_public_hashes_names_and_strips_secrets() -> None:
    data = {
        "Config": {
            "Name": "My Server",
            "ServerApiToken": "s3cr3t",
            "Admins": ["Alice", "Bob"],
            "MaxConnections": 60,
        }
    }
    out = redact_config(data, RedactionLevel.PUBLIC)
    cfg = out["Config"]
    assert cfg["ServerApiToken"] == SECRET_SENTINEL
    assert cfg["Name"] == hash_name("My Server")
    assert cfg["Admins"] == [hash_name("Alice"), hash_name("Bob")]
    # Non-name, non-secret scalars pass through untouched.
    assert cfg["MaxConnections"] == 60


def test_redact_operator_shows_names_strips_secrets() -> None:
    data = {"Config": {"Name": "My Server", "BotToken": "abc"}}
    out = redact_config(data, RedactionLevel.OPERATOR)
    assert out["Config"]["Name"] == "My Server"
    assert out["Config"]["BotToken"] == SECRET_SENTINEL


def test_redact_raw_discloses_everything() -> None:
    data = {"Config": {"Name": "My Server", "BotToken": "abc"}}
    out = redact_config(data, RedactionLevel.RAW)
    assert out["Config"]["Name"] == "My Server"
    assert out["Config"]["BotToken"] == "abc"


def test_secret_key_wins_over_name_key() -> None:
    # DiscordToken matches both the name regex (discord) and the secret regex
    # (token). It must be stripped, never merely hashed.
    data = {"DiscordToken": "tok"}
    assert redact_config(data, RedactionLevel.PUBLIC)["DiscordToken"] == SECRET_SENTINEL
    assert redact_config(data, RedactionLevel.OPERATOR)["DiscordToken"] == SECRET_SENTINEL


def test_hash_name_is_stable_and_non_reversible() -> None:
    assert hash_name("Alice") == hash_name("Alice")
    assert hash_name("Alice") != hash_name("Bob")
    assert "Alice" not in hash_name("Alice")


def test_coerce_level_defaults_and_validates() -> None:
    assert coerce_level(None) is RedactionLevel.OPERATOR
    assert coerce_level("") is RedactionLevel.OPERATOR
    assert coerce_level("PUBLIC") is RedactionLevel.PUBLIC
    with pytest.raises(ValueError):
        coerce_level("god-mode")


def test_raw_allowed_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ECO_ADMIN_ALLOW_RAW", raising=False)
    assert raw_allowed() is False
    monkeypatch.setenv("ECO_ADMIN_ALLOW_RAW", "1")
    assert raw_allowed() is True
    monkeypatch.setenv("ECO_ADMIN_ALLOW_RAW", "no")
    assert raw_allowed() is False


# --------------------------------------------------------------------------- #
# StateStore filesystem tests                                                  #
# --------------------------------------------------------------------------- #


def test_save_status_reports_size_and_age(state_dir: Path) -> None:
    store = StateStore(state_dir)
    payload = store.save_status(now=NOW)
    by_label = {f["label"]: f for f in payload["files"]}
    assert by_label["Game.eco"]["present"] is True
    assert by_label["Game.eco"]["sizeBytes"] > 0
    assert by_label["Game.eco"]["ageSeconds"] == pytest.approx(3600.0)
    assert by_label["Game.db"]["ageSeconds"] == pytest.approx(1800.0)


def test_save_status_marks_missing_file(tmp_path: Path) -> None:
    store = StateStore(tmp_path)  # empty dir, no Storage/
    payload = store.save_status(now=NOW)
    assert all(f["present"] is False for f in payload["files"])


def test_backup_list_counts_cadence_and_extremes(state_dir: Path) -> None:
    store = StateStore(state_dir)
    payload = store.backup_list(now=NOW)
    assert payload["count"] == 3
    assert payload["cadenceSeconds"] == pytest.approx(1800.0)
    assert payload["newest"]["label"] == "backup-2026-07-05-0200.eco"
    assert payload["oldest"]["label"] == "backup-2026-07-05-0100.eco"
    # backups list is newest-first.
    assert payload["backups"][0]["label"] == "backup-2026-07-05-0200.eco"


def test_backup_list_empty_dir(tmp_path: Path) -> None:
    payload = StateStore(tmp_path).backup_list(now=NOW)
    assert payload["count"] == 0
    assert payload["cadenceSeconds"] is None
    assert payload["newest"] is None


def test_read_config_rejects_unknown_name(state_dir: Path) -> None:
    with pytest.raises(KeyError):
        StateStore(state_dir).read_config("../../etc/passwd")
    with pytest.raises(KeyError):
        StateStore(state_dir).read_config("nonsense")


def test_read_config_parses_json(state_dir: Path) -> None:
    result = StateStore(state_dir).read_config("network")
    assert result["present"] is True
    assert result["format"] == "json"
    assert result["content"]["Config"]["Name"] == "Eco via Sirens (sample)"


def test_from_env_requires_state_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ECO_STATE_DIR", raising=False)
    with pytest.raises(RuntimeError):
        StateStore.from_env()


# --------------------------------------------------------------------------- #
# MCP tool surface tests                                                       #
# --------------------------------------------------------------------------- #


async def _call(store: StateStore, name: str, arguments: dict) -> mt.CallToolResult:
    server = build_admin_server(store)
    handler = server.request_handlers[mt.CallToolRequest]
    req = mt.CallToolRequest(
        method="tools/call",
        params=mt.CallToolRequestParams(name=name, arguments=arguments),
    )
    result = await handler(req)
    return result.root  # type: ignore[return-value]


def _json_block(result: mt.CallToolResult) -> dict:
    for block in result.content:
        text = getattr(block, "text", "") or ""
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            continue
    raise AssertionError("no JSON block in tool result")


@pytest.mark.asyncio
async def test_list_tools_advertises_admin_tools(state_dir: Path) -> None:
    server = build_admin_server(StateStore(state_dir))
    handler = server.request_handlers[mt.ListToolsRequest]
    result = await handler(mt.ListToolsRequest(method="tools/list"))
    names = {t.name for t in result.root.tools}
    assert names == {"eco_save_status", "eco_backup_list", "eco_config_get"}
    # eco_config_get exposes an enum of names, never a free-form path field.
    cfg_tool = next(t for t in result.root.tools if t.name == "eco_config_get")
    props = cfg_tool.inputSchema["properties"]
    assert "enum" in props["name"]
    assert "network" in props["name"]["enum"]


@pytest.mark.asyncio
async def test_config_get_operator_strips_secrets_shows_names(state_dir: Path) -> None:
    result = await _call(StateStore(state_dir), "eco_config_get", {"name": "network"})
    payload = _json_block(result)
    cfg = payload["content"]["Config"]
    assert cfg["ServerApiToken"] == SECRET_SENTINEL
    assert cfg["Name"] == "Eco via Sirens (sample)"


@pytest.mark.asyncio
async def test_config_get_public_hashes_names(state_dir: Path) -> None:
    result = await _call(
        StateStore(state_dir), "eco_config_get", {"name": "users", "level": "public"}
    )
    payload = _json_block(result)
    admins = payload["content"]["Config"]["Admins"]
    assert admins == [hash_name("SampleAdminOne"), hash_name("SampleAdminTwo")]


@pytest.mark.asyncio
async def test_config_get_raw_denied_by_default(
    state_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ECO_ADMIN_ALLOW_RAW", raising=False)
    result = await _call(
        StateStore(state_dir), "eco_config_get", {"name": "discord", "level": "raw"}
    )
    assert result.isError is True
    payload = _json_block(result)
    assert "denied" in payload["message"].lower()


@pytest.mark.asyncio
async def test_config_get_raw_allowed_with_flag(
    state_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ECO_ADMIN_ALLOW_RAW", "1")
    result = await _call(
        StateStore(state_dir), "eco_config_get", {"name": "discord", "level": "raw"}
    )
    assert result.isError is None or result.isError is False
    payload = _json_block(result)
    assert payload["content"]["Config"]["BotToken"] == "example-discord-bot-token-not-real"


@pytest.mark.asyncio
async def test_config_get_unknown_name_is_error(state_dir: Path) -> None:
    result = await _call(StateStore(state_dir), "eco_config_get", {"name": "../../secrets"})
    assert result.isError is True


@pytest.mark.asyncio
async def test_config_get_unknown_level_is_error(state_dir: Path) -> None:
    result = await _call(
        StateStore(state_dir), "eco_config_get", {"name": "network", "level": "god"}
    )
    assert result.isError is True


@pytest.mark.asyncio
async def test_save_status_tool(state_dir: Path) -> None:
    result = await _call(StateStore(state_dir), "eco_save_status", {})
    payload = _json_block(result)
    assert payload["level"] == "operator"
    assert any(f["label"] == "Game.eco" and f["present"] for f in payload["files"])


@pytest.mark.asyncio
async def test_backup_list_tool_hashes_names_at_public(state_dir: Path) -> None:
    result = await _call(StateStore(state_dir), "eco_backup_list", {"level": "public"})
    payload = _json_block(result)
    assert payload["count"] == 3
    # At public the backup filename (which can embed a world name) is hashed.
    assert payload["newest"]["label"].startswith("[hashed:")


# --------------------------------------------------------------------------- #
# Feature-flag wiring                                                          #
# --------------------------------------------------------------------------- #


def _route_paths(app: object) -> set[str | None]:
    return {getattr(r, "path", None) for r in app.routes}  # type: ignore[attr-defined]


def test_admin_mount_absent_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ECO_ADMIN_ENABLED", raising=False)
    from eco_mcp_app.http_app import create_app

    app = create_app()
    assert "/admin" not in _route_paths(app)


def test_admin_mount_present_when_flag_on(monkeypatch: pytest.MonkeyPatch, state_dir: Path) -> None:
    monkeypatch.setenv("ECO_ADMIN_ENABLED", "1")
    monkeypatch.setenv("ECO_STATE_DIR", str(state_dir))
    from eco_mcp_app.http_app import create_app

    app = create_app()
    assert "/admin" in _route_paths(app)
