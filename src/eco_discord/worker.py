"""Pycord gateway entrypoint. Registration deliberately lives elsewhere."""

from __future__ import annotations

import logging
import os
from typing import Any

from eco_mcp_app.telemetry import init_telemetry, record_exception

from .client import EcoAppClient
from .commands import CommandService
from .embeds import EmbedFactory


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _required_channel_id(name: str) -> int:
    value = _required(name)
    try:
        channel_id = int(value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a Discord channel id") from error
    if channel_id <= 0:
        raise RuntimeError(f"{name} must be a positive Discord channel id")
    return channel_id


def build_bot() -> Any:
    import discord

    service = CommandService(
        EcoAppClient(_required("ECO_DISCORD_ECO_APP_URL")),
        EmbedFactory(os.getenv("ECO_DISCORD_SERVER_LABEL", "Eco")),
        _required("ECO_DISCORD_PUBLIC_URL"),
        _required_channel_id("ECO_DISCORD_INFO_CHANNEL_ID"),
    )
    bot = discord.Bot(intents=discord.Intents.none())
    eco = bot.create_group("eco", "Read-only Eco server information")
    rich = eco.create_subgroup("rich", "Rich previews in #eco-app")

    @rich.command(name="status", description="Current server status")
    async def status(ctx: discord.ApplicationContext) -> None:
        await service.resolve_interaction(ctx.interaction, "status")

    @rich.command(name="world", description="World and climate summary")
    async def world(ctx: discord.ApplicationContext) -> None:
        await service.resolve_interaction(ctx.interaction, "world")

    @rich.command(name="economy", description="Currency, trade, and supply highlights")
    async def economy(ctx: discord.ApplicationContext) -> None:
        await service.resolve_interaction(ctx.interaction, "economy")

    @rich.command(name="player", description="Public citizen dossier")
    async def player(ctx: discord.ApplicationContext, name: str) -> None:
        await service.resolve_interaction(ctx.interaction, "player", name)

    @rich.command(name="help", description="Eco command directory")
    async def help_command(ctx: discord.ApplicationContext) -> None:
        await service.resolve_interaction(ctx.interaction, "help")

    return bot


def main() -> None:
    logging.basicConfig(level=os.getenv("ECO_DISCORD_LOG_LEVEL", "INFO"))
    init_telemetry()
    bot = build_bot()
    logging.getLogger(__name__).info("discord_worker_starting")
    try:
        bot.run(_required("ECO_DISCORD_TOKEN"))  # type: ignore[attr-defined]
    except Exception as exc:
        record_exception(exc, "eco.discord.worker")
        raise


if __name__ == "__main__":
    main()
