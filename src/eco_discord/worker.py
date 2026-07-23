"""Pycord gateway entrypoint. Registration deliberately lives elsewhere."""

from __future__ import annotations

import logging
import os
from typing import Any

from eco_mcp_app.telemetry import init_sentry

from .client import EcoAppClient
from .commands import CommandService
from .embeds import EmbedFactory


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def build_bot() -> Any:
    import discord

    service = CommandService(
        EcoAppClient(_required("ECO_DISCORD_ECO_APP_URL")),
        EmbedFactory(os.getenv("ECO_DISCORD_SERVER_LABEL", "Eco")),
        _required("ECO_DISCORD_PUBLIC_URL"),
    )
    bot = discord.Bot(intents=discord.Intents.none())
    eco = bot.create_group("eco", "Read-only Eco server information")

    @eco.command(name="status", description="Current server status")
    async def status(ctx: discord.ApplicationContext) -> None:
        await service.resolve_interaction(ctx.interaction, "status")

    @eco.command(name="world", description="World and climate summary")
    async def world(ctx: discord.ApplicationContext) -> None:
        await service.resolve_interaction(ctx.interaction, "world")

    @eco.command(name="economy", description="Currency, trade, and supply highlights")
    async def economy(ctx: discord.ApplicationContext) -> None:
        await service.resolve_interaction(ctx.interaction, "economy")

    @eco.command(name="player", description="Public citizen dossier")
    async def player(ctx: discord.ApplicationContext, name: str) -> None:
        await service.resolve_interaction(ctx.interaction, "player", name)

    @eco.command(name="help", description="Eco command directory")
    async def help_command(ctx: discord.ApplicationContext) -> None:
        await service.resolve_interaction(ctx.interaction, "help")

    return bot


def main() -> None:
    logging.basicConfig(level=os.getenv("ECO_DISCORD_LOG_LEVEL", "INFO"))
    init_sentry()
    bot = build_bot()
    logging.getLogger(__name__).info("discord_worker_starting")
    bot.run(_required("ECO_DISCORD_TOKEN"))  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()
