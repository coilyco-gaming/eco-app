"""Bounded read-only probes of the node-local Eco HTTP surface."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

RUNTIME_BASE_URL_ENV = "ECO_ADMIN_BASE_URL"
RUNTIME_TIMEOUT_ENV = "ECO_ADMIN_HTTP_TIMEOUT_SECONDS"
DEFAULT_BASE_URL = "http://127.0.0.1:3001"
DEFAULT_TIMEOUT = 5.0
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class EcoRuntimeClient:
    """Read Eco's fixed ``/info`` route with a bounded response budget."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        resolved_base = base_url or os.environ.get(RUNTIME_BASE_URL_ENV) or DEFAULT_BASE_URL
        self.base_url = resolved_base.rstrip("/")
        raw_timeout = os.environ.get(RUNTIME_TIMEOUT_ENV)
        self.timeout = timeout if timeout is not None else float(raw_timeout or DEFAULT_TIMEOUT)
        if not 0.1 <= self.timeout <= 30:
            raise ValueError(f"{RUNTIME_TIMEOUT_ENV} must be from 0.1 to 30 seconds.")
        self.transport = transport

    async def _info(self) -> tuple[dict[str, Any], float]:
        started = time.monotonic()
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self.transport,
        ) as client:
            async with client.stream("GET", "/info") as response:
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise RuntimeError(
                            f"Eco /info response exceeds {MAX_RESPONSE_BYTES} bytes."
                        )
        try:
            payload = httpx.Response(200, content=bytes(body)).json()
        except ValueError as exc:
            raise RuntimeError("Eco /info returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Eco /info returned a non-object JSON payload.")
        return payload, round((time.monotonic() - started) * 1000, 3)

    async def live_status(self) -> dict[str, Any]:
        try:
            payload, latency_ms = await self._info()
        except (httpx.HTTPError, OSError) as exc:
            raise RuntimeError("Eco /info is unavailable.") from exc
        # Keep the public Eco schema intact enough to remain useful. Redaction
        # happens at the MCP layer after this fixed read completes.
        return {
            "source": f"{self.base_url}/info",
            "latencyMs": latency_ms,
            "status": payload,
        }

    async def service_health(self) -> dict[str, Any]:
        try:
            payload, latency_ms = await self._info()
        except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
            return {
                "source": f"{self.base_url}/info",
                "reachable": False,
                "detail": type(exc).__name__,
            }
        return {
            "source": f"{self.base_url}/info",
            "reachable": True,
            "latencyMs": latency_ms,
            "version": payload.get("Version"),
        }


__all__ = ["EcoRuntimeClient"]
