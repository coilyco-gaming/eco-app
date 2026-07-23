"""Bounded HTTP client for the public eco-app data plane."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


class EcoAppError(Exception):
    """Safe public error: details remain in structured logs, never embeds."""


@dataclass
class EcoAppClient:
    base_url: str
    timeout: float = 8.0

    async def get(self, path: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url.rstrip("/"),
                timeout=httpx.Timeout(self.timeout, connect=min(3.0, self.timeout)),
            ) as client:
                response = await client.get(path)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EcoAppError("eco-app unavailable") from exc
        if not isinstance(data, dict) or data.get("error"):
            raise EcoAppError("eco-app returned incomplete data")
        return data

    async def status(self) -> dict[str, Any]:
        return await self.get("/preview.json")

    async def world(self) -> dict[str, Any]:
        return await self.get("/preview/world.json")

    async def economy(self) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        import asyncio

        return tuple(
            await asyncio.gather(
                self.get("/preview/currency.json"),
                self.get("/preview/logistics.json"),
                self.get("/preview/market.json"),
            )
        )  # type: ignore[return-value]

    async def player(self, name: str) -> dict[str, Any]:
        return await self.get(f"/preview/user.json?name={quote(name, safe='')}")
