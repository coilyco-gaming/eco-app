"""Explicit guild-scoped Discord command registration operation."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

COMMAND_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "eco",
        "description": "Read-only Eco server information",
        "type": 1,
        "options": [
            {
                "name": "rich",
                "description": "Rich previews in #eco-app",
                "type": 2,
                "options": [
                    {"name": "status", "description": "Current server status", "type": 1},
                    {"name": "world", "description": "World and climate summary", "type": 1},
                    {
                        "name": "economy",
                        "description": "Currency, trade, and supply highlights",
                        "type": 1,
                    },
                    {
                        "name": "player",
                        "description": "Public citizen dossier",
                        "type": 1,
                        "options": [
                            {
                                "name": "name",
                                "description": "Citizen name",
                                "type": 3,
                                "required": True,
                            }
                        ],
                    },
                    {"name": "help", "description": "Eco command directory", "type": 1},
                ],
            },
        ],
    }
]


async def register_test_guild() -> None:
    token = os.environ["ECO_DISCORD_TOKEN"]
    app_id = os.environ["ECO_DISCORD_APPLICATION_ID"]
    guild_id = os.environ["ECO_DISCORD_TEST_GUILD_ID"]
    url = f"https://discord.com/api/v10/applications/{app_id}/guilds/{guild_id}/commands"
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0)) as client:
        response = await client.put(
            url, headers={"Authorization": f"Bot {token}"}, json=COMMAND_SCHEMA
        )
        response.raise_for_status()


def main() -> None:
    asyncio.run(register_test_guild())


if __name__ == "__main__":
    main()
