"""Enum-only, read-only Eco RCON client.

Eco RCON accepts every server command, so the security boundary lives here:
the caller chooses one of twelve audited query names and can never submit a
command string. One in-process lock serializes calls because Eco supports one
active RCON client.
"""

from __future__ import annotations

import asyncio
import logging
import os
import struct
import time
from enum import StrEnum
from typing import ClassVar

RCON_HOST_ENV = "ECO_RCON_HOST"
RCON_PORT_ENV = "ECO_RCON_PORT"
RCON_PASSWORD_ENV = "ECO_RCON_PASSWORD"
RCON_TIMEOUT_ENV = "ECO_RCON_TIMEOUT_SECONDS"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3002
DEFAULT_TIMEOUT = 5.0
MAX_PACKET_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024

logger = logging.getLogger(__name__)


class RconQuery(StrEnum):
    ONLINE_PLAYERS = "online_players"
    METEOR_STATUS = "meteor_status"
    WORLD_TIME = "world_time"
    CLIMATE_STATUS = "climate_status"
    SEA_LEVEL = "sea_level"
    POPULATION_CHANGES = "population_changes"
    ACTIVE_ELECTIONS = "active_elections"
    GOVERNMENT = "government"
    CIVICS_TICK = "civics_tick"
    CURRENCIES = "currencies"
    WEATHER_STATUS = "weather_status"
    INITIAL_SPAWN_POSITIONS = "initial_spawn_positions"


RCON_COMMANDS: dict[RconQuery, str] = {
    RconQuery.ONLINE_PLAYERS: "manage players",
    RconQuery.METEOR_STATUS: "meteor status",
    RconQuery.WORLD_TIME: "time now",
    RconQuery.CLIMATE_STATUS: "climate status",
    RconQuery.SEA_LEVEL: "sim sealevel",
    RconQuery.POPULATION_CHANGES: "sim showpopulationchanges",
    RconQuery.ACTIVE_ELECTIONS: "civics elections",
    RconQuery.GOVERNMENT: "civics showgovernment",
    RconQuery.CIVICS_TICK: "civics showtick",
    RconQuery.CURRENCIES: "money currencies",
    RconQuery.WEATHER_STATUS: "weather status",
    RconQuery.INITIAL_SPAWN_POSITIONS: "initialspawn list",
}

PUBLIC_DENY = {
    RconQuery.ONLINE_PLAYERS,
    RconQuery.ACTIVE_ELECTIONS,
    RconQuery.GOVERNMENT,
}


class RconError(RuntimeError):
    """A bounded RCON protocol, auth, or availability failure."""


def coerce_query(value: object) -> RconQuery:
    try:
        return RconQuery(str(value))
    except ValueError as exc:
        allowed = ", ".join(item.value for item in RconQuery)
        raise ValueError(f"unknown RCON query {value!r}; expected one of: {allowed}") from exc


def _packet(request_id: int, packet_type: int, payload: str) -> bytes:
    encoded = payload.encode("utf-8")
    body = struct.pack("<ii", request_id, packet_type) + encoded + b"\x00\x00"
    return struct.pack("<i", len(body)) + body


async def _read_packet(reader: asyncio.StreamReader, timeout: float) -> tuple[int, int, str]:
    try:
        header = await asyncio.wait_for(reader.readexactly(4), timeout)
    except (TimeoutError, asyncio.IncompleteReadError) as exc:
        raise RconError("RCON response header timed out or closed early.") from exc
    (size,) = struct.unpack("<i", header)
    if not 10 <= size <= MAX_PACKET_BYTES:
        raise RconError(f"RCON packet size {size} is outside the safe bound.")
    try:
        body = await asyncio.wait_for(reader.readexactly(size), timeout)
    except (TimeoutError, asyncio.IncompleteReadError) as exc:
        raise RconError("RCON response body timed out or closed early.") from exc
    request_id, packet_type = struct.unpack("<ii", body[:8])
    payload = body[8:-2].decode("utf-8", errors="replace")
    return request_id, packet_type, payload


class EcoRconClient:
    """Small Source-RCON client with a process-wide single-client lock."""

    _lock: ClassVar[asyncio.Lock | None] = None

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        password: str | None = None,
        *,
        timeout: float | None = None,
    ) -> None:
        self.host = host or os.environ.get(RCON_HOST_ENV) or DEFAULT_HOST
        self.port = port if port is not None else int(os.environ.get(RCON_PORT_ENV) or DEFAULT_PORT)
        self.password = password if password is not None else os.environ.get(RCON_PASSWORD_ENV)
        raw_timeout = os.environ.get(RCON_TIMEOUT_ENV)
        self.timeout = timeout if timeout is not None else float(raw_timeout or DEFAULT_TIMEOUT)
        if not 1 <= self.port <= 65535:
            raise ValueError(f"{RCON_PORT_ENV} must be from 1 to 65535.")
        if not 0.1 <= self.timeout <= 30:
            raise ValueError(f"{RCON_TIMEOUT_ENV} must be from 0.1 to 30 seconds.")

    @classmethod
    def _query_lock(cls) -> asyncio.Lock:
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @property
    def configured(self) -> bool:
        return bool(self.password)

    async def query(self, query: RconQuery) -> dict[str, object]:
        if not self.password:
            raise RconError(f"{RCON_PASSWORD_ENV} is unset.")
        command = RCON_COMMANDS[query]
        started = time.monotonic()
        outcome = "error"
        async with self._query_lock():
            writer: asyncio.StreamWriter | None = None
            try:
                reader, opened_writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port),
                    self.timeout,
                )
                writer = opened_writer
                opened_writer.write(_packet(1, 3, self.password))
                await asyncio.wait_for(opened_writer.drain(), self.timeout)
                authenticated = False
                for _ in range(2):
                    request_id, packet_type, _ = await _read_packet(reader, self.timeout)
                    if request_id == -1:
                        raise RconError("RCON authentication failed.")
                    if request_id == 1 and packet_type == 2:
                        authenticated = True
                        break
                if not authenticated:
                    raise RconError("RCON authentication response was not received.")

                opened_writer.write(_packet(2, 2, command))
                await asyncio.wait_for(opened_writer.drain(), self.timeout)
                request_id, _, payload = await _read_packet(reader, self.timeout)
                if request_id != 2:
                    raise RconError("RCON command response used an unexpected request id.")
                if len(payload.encode("utf-8")) > MAX_RESPONSE_BYTES:
                    raise RconError("RCON response exceeds the safe output bound.")
                outcome = "ok"
                return {
                    "query": query.value,
                    "response": payload,
                    "latencyMs": round((time.monotonic() - started) * 1000, 3),
                }
            except (OSError, TimeoutError) as exc:
                raise RconError("RCON connection failed or timed out.") from exc
            finally:
                if writer is not None:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except OSError:
                        pass
                logger.info(
                    "eco_admin_rcon query=%s outcome=%s latency_ms=%.3f",
                    query.value,
                    outcome,
                    (time.monotonic() - started) * 1000,
                )


__all__ = [
    "PUBLIC_DENY",
    "RCON_COMMANDS",
    "EcoRconClient",
    "RconError",
    "RconQuery",
    "coerce_query",
]
