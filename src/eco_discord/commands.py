"""Command service: data-plane mapping and exactly-one-embed interaction flow."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from .client import EcoAppClient, EcoAppError
from .embeds import EmbedFactory, EmbedField, EmbedPayload

LOG = logging.getLogger(__name__)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


@dataclass(frozen=True)
class CommandService:
    client: EcoAppClient
    embeds: EmbedFactory
    public_url: str

    def _url(self, path: str) -> str:
        return f"{self.public_url.rstrip('/')}{path}"

    async def render(self, command: str, name: str | None = None) -> EmbedPayload:
        try:
            if command == "status":
                return self._status(await self.client.status())
            if command == "world":
                return self._world(await self.client.world())
            if command == "economy":
                return self._economy(*(await self.client.economy()))
            if command == "player" and name:
                return self._player(name, await self.client.player(name))
            if command == "help":
                return self._help()
            return self._error(command)
        except (TimeoutError, EcoAppError):
            return self._error(command)
        except Exception:
            LOG.exception("discord_command_unexpected", extra={"command": command})
            return self._error(command)

    async def resolve_interaction(
        self, interaction: object, command: str, name: str | None = None
    ) -> None:
        """Defer before every fetch, then make exactly one embed-only edit."""
        started = time.monotonic()
        await interaction.response.defer()  # type: ignore[attr-defined]
        payload = await self.render(command, name)
        await interaction.edit_original_response(  # type: ignore[attr-defined]
            embed=self.embeds.to_discord(payload), content=None
        )
        LOG.info(
            "discord_command_complete",
            extra={
                "command": command,
                "outcome": payload.kind,
                "duration_ms": int((time.monotonic() - started) * 1000),
            },
        )

    def _status(self, data: dict[str, Any]) -> EmbedPayload:
        players = _mapping(data.get("players"))
        cycle = _mapping(data.get("cycle"))
        server = _mapping(data.get("server"))
        return self.embeds.success(
            title="Eco server status",
            url=self._url("/info"),
            description="Current Sirens server state.",
            fields=[
                EmbedField(
                    "Players online",
                    f"{players.get('online', 0)} / {players.get('total', 0)}",
                    True,
                ),
                EmbedField("World age", f"Day {cycle.get('daysRunning', 0)}", True),
                EmbedField("Meteor", f"{cycle.get('daysUntilMeteor', 0)} days remaining", True),
                EmbedField("Version", str(server.get("version") or "Unavailable"), True),
            ],
        )

    def _world(self, data: dict[str, Any]) -> EmbedPayload:
        summary = str(
            data.get("narrative") or data.get("summary") or "World and climate data are live."
        )
        return self.embeds.success(title="Eco world", url=self._url("/map"), description=summary)

    def _economy(
        self, currency: dict[str, Any], logistics: dict[str, Any], market: dict[str, Any]
    ) -> EmbedPayload:
        money = _mapping(currency.get("money"))
        gaps = logistics.get("supplyGaps") or logistics.get("gaps") or []
        fields = [EmbedField("Active currencies", str(money.get("activeCurrencies", 0)), True)]
        if isinstance(gaps, list):
            fields.append(EmbedField("Supply gaps", str(len(gaps)), True))
        fields.append(EmbedField("Market items", str(len(market.get("items") or [])), True))
        return self.embeds.success(
            title="Eco economy",
            url=self._url("/trade"),
            description=str(
                currency.get("narrative") or "Current trade, currency, and supply highlights."
            ),
            fields=fields,
        )

    def _player(self, name: str, data: dict[str, Any]) -> EmbedPayload:
        encoded = quote(name.encode("utf-8").hex())
        if not data.get("found"):
            return self.embeds.empty(
                title="Eco player",
                url=self._url(f"/users/{encoded}"),
                description="No public dossier data is available for that citizen yet.",
            )
        section_keys = ("jobs", "trades", "crafting", "civics", "currency", "world")
        sections = [key for key in section_keys if data.get(key)]
        return self.embeds.success(
            title=f"Eco player: {name}",
            url=self._url(f"/users/{encoded}"),
            description="Public citizen dossier summary.",
            fields=[EmbedField("Available activity", ", ".join(sections) or "Limited", False)],
        )

    def _help(self) -> EmbedPayload:
        return self.embeds.success(
            title="Eco command help",
            url=self._url("/"),
            description=(
                "Use /eco status, world, economy, player, or help. "
                "Every command links to its full Eco page."
            ),
        )

    def _error(self, command: str) -> EmbedPayload:
        paths = {"status": "/info", "world": "/map", "economy": "/trade", "player": "/"}
        return self.embeds.error(
            title="Eco data temporarily unavailable",
            url=self._url(paths.get(command, "/")),
            description="Eco could not refresh this view. Try again shortly or open the live site.",
        )
