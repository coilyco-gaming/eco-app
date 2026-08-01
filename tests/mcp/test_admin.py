"""Tests for the privileged, read-only /admin Eco MCP.

Everything runs against a local sample state checkout copied from
``tests/mcp/fixtures/eco_state`` into ``tmp_path`` with deterministic mtimes,
so save ages and backup cadence are stable. No live server is touched.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import struct
from pathlib import Path

import httpx
import mcp.types as mt
import pytest

from eco_mcp_app.admin import (
    RCON_COMMANDS,
    EcoRconClient,
    EcoRuntimeClient,
    RconQuery,
    RedactionLevel,
    StateStore,
    build_admin_server,
)
from eco_mcp_app.admin.rcon import RconError, coerce_query
from eco_mcp_app.admin.redaction import (
    SECRET_SENTINEL,
    coerce_level,
    hash_name,
    raw_allowed,
    redact_config,
    redact_text,
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
    replay_file = root / "Storage" / "EcoReplay.jsonl"
    replay_rows = [
        {
            "id": 1,
            "unixTime": NOW - 120,
            "gameTime": 10,
            "type": "Craft",
            "citizen": "SampleAdminOne",
            "body": '{"ItemName":"Brick"}',
        },
        {
            "id": 2,
            "unixTime": NOW - 60,
            "gameTime": 11,
            "type": "Vote",
            "citizen": "SampleAdminTwo",
            "body": '{"Choice":"Yes"}',
        },
        {
            "id": 3,
            "unixTime": NOW - 30,
            "gameTime": 12,
            "type": "Chat",
            "citizen": "SampleAdminOne",
            "body": '{"Message":"hello","ApiToken":"not-real"}',
        },
    ]
    replay_file.write_text(
        "\n".join(json.dumps(row) for row in replay_rows) + "\n", encoding="utf-8"
    )
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


def test_redact_text_strips_assignments_but_preserves_operator_context() -> None:
    text = "request token=abc accepted"
    assert redact_text(text, RedactionLevel.OPERATOR) == f"request token={SECRET_SENTINEL} accepted"
    assert redact_text(text, RedactionLevel.RAW) == text


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


def test_world_meta_selects_known_fields_only(state_dir: Path) -> None:
    result = StateStore(state_dir).world_meta()
    assert result["present"] is True
    assert result["metadata"]["Seed"] == "sample-seed"
    assert result["metadata"]["Width"] == 140
    assert "InternalTuning" not in result["metadata"]


def test_config_diff_reads_fixed_current_and_diff(state_dir: Path) -> None:
    result = StateStore(state_dir).config_diff("network")
    assert result["current"]["present"] is True
    assert result["diff"]["present"] is True
    with pytest.raises(KeyError):
        StateStore(state_dir).config_diff("../../etc/passwd")


def test_mod_configs_reads_fixed_group(state_dir: Path) -> None:
    result = StateStore(state_dir).mod_configs()
    configs = {item["name"]: item for item in result["configs"]}
    assert configs["mighty_moose"]["present"] is True
    assert configs["nid_toolbox"]["present"] is False


def test_events_recent_reads_jsonl_read_only(state_dir: Path) -> None:
    store = StateStore(state_dir)
    result = store.events_recent(2)
    assert result["source"] == "Storage/EcoReplay.jsonl"
    assert [event["id"] for event in result["events"]] == [3, 2]
    with pytest.raises(ValueError):
        store.events_recent(201)


def test_player_activity_aggregates_bounded_sample(state_dir: Path) -> None:
    result = StateStore(state_dir).player_activity(3)
    players = {item["citizen"]: item for item in result["players"]}
    assert players["SampleAdminOne"]["eventCount"] == 2
    assert players["SampleAdminOne"]["actions"]["Craft"] == 1


def test_log_reads_fixed_stream_literal_and_bounded(state_dir: Path) -> None:
    store = StateStore(state_dir)
    tail = store.log_tail("web", 2)
    assert tail["source"] == "Logs/Web/web.txt"
    assert tail["lineCount"] == 2
    found = store.log_grep("web", "REQUEST", 10)
    assert found["matchCount"] == 2
    with pytest.raises(KeyError):
        store.log_tail("../../etc", 10)
    with pytest.raises(ValueError):
        store.log_grep("web", "x" * 121, 10)


def test_mod_inventory_reports_manifest_version(state_dir: Path) -> None:
    result = StateStore(state_dir).mods_installed()
    sample = next(item for item in result["mods"] if item["name"] == "SampleMod")
    assert sample["version"] == "1.2.3"


def test_from_env_requires_state_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ECO_STATE_DIR", raising=False)
    with pytest.raises(RuntimeError):
        StateStore.from_env()


# --------------------------------------------------------------------------- #
# MCP tool surface tests                                                       #
# --------------------------------------------------------------------------- #


async def _call(
    store: StateStore,
    name: str,
    arguments: dict,
    *,
    rcon: EcoRconClient | None = None,
    runtime: EcoRuntimeClient | None = None,
) -> mt.CallToolResult:
    server = build_admin_server(store, rcon=rcon, runtime=runtime)
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
    assert names == {
        "eco_save_status",
        "eco_backup_list",
        "eco_world_meta",
        "eco_config_get",
        "eco_config_diff",
        "eco_mod_configs",
        "eco_events_recent",
        "eco_player_activity",
        "eco_log_tail",
        "eco_log_grep",
        "eco_mods_installed",
        "eco_live_status",
        "eco_service_health",
        "eco_rcon_query",
    }
    # eco_config_get exposes an enum of names, never a free-form path field.
    cfg_tool = next(t for t in result.root.tools if t.name == "eco_config_get")
    props = cfg_tool.inputSchema["properties"]
    assert "enum" in props["name"]
    assert "network" in props["name"]["enum"]
    rcon_tool = next(t for t in result.root.tools if t.name == "eco_rcon_query")
    assert rcon_tool.inputSchema["properties"]["query"]["enum"] == [
        item.value for item in RconQuery
    ]
    assert len(rcon_tool.inputSchema["properties"]["query"]["enum"]) == 12
    assert "command" not in rcon_tool.inputSchema["properties"]


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


@pytest.mark.asyncio
async def test_disk_group_tools_redact_structured_content(state_dir: Path) -> None:
    store = StateStore(state_dir)
    diff = _json_block(
        await _call(store, "eco_config_diff", {"name": "network", "level": "operator"})
    )
    assert diff["diff"]["content"]["Config"]["ServerApiToken"] == SECRET_SENTINEL
    mods = _json_block(await _call(store, "eco_mod_configs", {}))
    mighty = next(item for item in mods["configs"] if item["name"] == "mighty_moose")
    assert mighty["content"]["Config"]["ApiKey"] == SECRET_SENTINEL
    events = _json_block(await _call(store, "eco_events_recent", {"level": "public"}))
    assert events["events"][0]["citizen"] == hash_name("SampleAdminOne")
    assert events["events"][0]["body"]["ApiToken"] == SECRET_SENTINEL
    activity = _json_block(await _call(store, "eco_player_activity", {"level": "public"}))
    assert all(item["citizen"].startswith("[hashed:") for item in activity["players"])


@pytest.mark.asyncio
async def test_log_tools_are_operator_only_and_strip_secret_values(state_dir: Path) -> None:
    store = StateStore(state_dir)
    denied = await _call(store, "eco_log_tail", {"stream": "web", "level": "public"})
    assert denied.isError is True
    payload = _json_block(await _call(store, "eco_log_tail", {"stream": "web", "lines": 3}))
    assert any(f"token={SECRET_SENTINEL}" in line for line in payload["lines"])
    assert all("not-a-real-token" not in line for line in payload["lines"])
    grep = _json_block(await _call(store, "eco_log_grep", {"stream": "web", "query": "TOKEN"}))
    assert grep["matchCount"] == 1
    assert grep["matches"][0]["text"].endswith("request accepted")


@pytest.mark.asyncio
async def test_mods_and_world_tools(state_dir: Path) -> None:
    store = StateStore(state_dir)
    world = _json_block(await _call(store, "eco_world_meta", {}))
    assert world["metadata"]["MeteorImpactDays"] == 30
    mods = _json_block(await _call(store, "eco_mods_installed", {}))
    assert mods["count"] == 1


@pytest.mark.asyncio
async def test_runtime_tools_use_fixed_info_route_and_redact_names(state_dir: Path) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "Version": "0.13-test",
                "OnlinePlayers": [{"Name": "SampleAdminOne"}],
            },
        )

    runtime = EcoRuntimeClient(
        "http://eco-runtime.invalid",
        transport=httpx.MockTransport(handler),
    )
    status = _json_block(
        await _call(
            StateStore(state_dir),
            "eco_live_status",
            {"level": "public"},
            runtime=runtime,
        )
    )
    assert status["status"]["OnlinePlayers"][0]["Name"] == hash_name("SampleAdminOne")
    health = _json_block(
        await _call(StateStore(state_dir), "eco_service_health", {}, runtime=runtime)
    )
    assert health["reachable"] is True
    assert health["version"] == "0.13-test"
    assert seen == ["/info", "/info"]


class StubRcon(EcoRconClient):
    def __init__(self) -> None:
        super().__init__(password="unused")
        self.queries: list[RconQuery] = []

    async def query(self, query: RconQuery) -> dict[str, object]:
        self.queries.append(query)
        return {
            "query": query.value,
            "response": "token=not-real Day 5",
            "latencyMs": 1.0,
        }


@pytest.mark.asyncio
async def test_rcon_tool_accepts_only_enum_and_redacts_output(state_dir: Path) -> None:
    rcon = StubRcon()
    result = _json_block(
        await _call(
            StateStore(state_dir),
            "eco_rcon_query",
            {"query": "world_time"},
            rcon=rcon,
        )
    )
    assert rcon.queries == [RconQuery.WORLD_TIME]
    assert result["response"] == f"token={SECRET_SENTINEL} Day 5"
    unknown = await _call(
        StateStore(state_dir),
        "eco_rcon_query",
        {"query": "kick SampleAdminOne"},
        rcon=rcon,
    )
    assert unknown.isError is True


@pytest.mark.asyncio
async def test_identity_rcon_queries_are_public_denied(state_dir: Path) -> None:
    result = await _call(
        StateStore(state_dir),
        "eco_rcon_query",
        {"query": "online_players", "level": "public"},
        rcon=StubRcon(),
    )
    assert result.isError is True


def _rcon_packet(request_id: int, packet_type: int, payload: str) -> bytes:
    body = struct.pack("<ii", request_id, packet_type) + payload.encode() + b"\x00\x00"
    return struct.pack("<i", len(body)) + body


async def _read_rcon_request(reader: asyncio.StreamReader) -> tuple[int, int, str]:
    (size,) = struct.unpack("<i", await reader.readexactly(4))
    body = await reader.readexactly(size)
    request_id, packet_type = struct.unpack("<ii", body[:8])
    return request_id, packet_type, body[8:-2].decode()


@pytest.mark.asyncio
async def test_rcon_protocol_authenticates_and_sends_exact_allowlisted_command() -> None:
    received: list[tuple[int, int, str]] = []

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        auth = await _read_rcon_request(reader)
        received.append(auth)
        writer.write(_rcon_packet(auth[0], 0, ""))
        writer.write(_rcon_packet(auth[0], 2, ""))
        await writer.drain()
        command = await _read_rcon_request(reader)
        received.append(command)
        writer.write(_rcon_packet(command[0], 0, "Day 12, 08:00"))
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        client = EcoRconClient(host="127.0.0.1", port=port, password="test", timeout=1)
        result = await client.query(RconQuery.WORLD_TIME)
    finally:
        server.close()
        await server.wait_closed()
    assert received == [
        (1, 3, "test"),
        (2, 2, RCON_COMMANDS[RconQuery.WORLD_TIME]),
    ]
    assert result["response"] == "Day 12, 08:00"


def test_rcon_enum_is_exact_twelve_command_core() -> None:
    assert {item.value for item in RconQuery} == {
        "online_players",
        "meteor_status",
        "world_time",
        "climate_status",
        "sea_level",
        "population_changes",
        "active_elections",
        "government",
        "civics_tick",
        "currencies",
        "weather_status",
        "initial_spawn_positions",
    }
    with pytest.raises(ValueError):
        coerce_query("shutdown")


@pytest.mark.asyncio
async def test_rcon_requires_password() -> None:
    client = EcoRconClient(password=None)
    client.password = None
    with pytest.raises(RconError):
        await client.query(RconQuery.WORLD_TIME)


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
