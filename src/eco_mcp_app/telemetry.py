"""Sentry SDK init for eco-mcp-app.

Mirrors the pattern in coilysiren/backend's telemetry.py. Called at process
startup from both the stdio entrypoint (__main__.py) and the ASGI entrypoint
(http_app.py) so errors get captured regardless of transport.

When SENTRY_DSN is set, initializes a real client with Starlette + FastAPI
integrations. Otherwise falls back to `sentry_sdk.init()` with no DSN, which
is a no-op that swallows captures silently. This keeps local dev quiet and
the production pod wired in via the ExternalSecret in deploy/main.yml.
"""

from __future__ import annotations

import logging
import os

import sentry_sdk
import sentry_sdk.integrations.fastapi as sentry_fastapi
import sentry_sdk.integrations.logging as sentry_logging
import sentry_sdk.integrations.starlette as sentry_starlette

_log = logging.getLogger(__name__)

_initialized = False


def init_sentry() -> None:
    """Idempotent. Safe to call from multiple entry points in the same process."""
    global _initialized
    if _initialized:
        return
    dsn = os.getenv("SENTRY_DSN")
    if dsn:
        try:
            sentry_sdk.init(
                dsn=dsn,
                enable_logs=True,
                integrations=[
                    sentry_starlette.StarletteIntegration(),
                    sentry_fastapi.FastApiIntegration(),
                    sentry_logging.LoggingIntegration(),
                ],
            )
        except Exception:
            # A truthy-but-malformed SENTRY_DSN (e.g. missing scheme) makes
            # sentry_sdk raise BadDsn. Telemetry misconfig must never crash the
            # service, so log-and-skip exactly as an unset DSN already does,
            # rather than crash-looping the pod at boot. See eco-app#43.
            #
            # Pass dsn="" (empty string), NOT a bare init() or dsn=None. Both of
            # those leave the resolved dsn as None, and sentry_sdk._get_options
            # then re-reads SENTRY_DSN from the environment (client.py:312) - the
            # same bad value that just failed, raising BadDsn again. An explicit
            # empty string is kept verbatim (not None), so no env re-read happens
            # and the empty dsn disables the transport cleanly.
            _log.warning("SENTRY_DSN is set but invalid; continuing without Sentry", exc_info=True)
            sentry_sdk.init(dsn="")
    else:
        sentry_sdk.init()
    _initialized = True
