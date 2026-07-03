"""Unit tests for ``init_sentry``.

Regression guard for eco-app#43: a malformed ``SENTRY_DSN`` (truthy but with
no scheme) made ``sentry_sdk.init`` raise ``BadDsn``, which crash-looped the
pod at boot. ``init_sentry`` must degrade gracefully instead, exactly as an
unset DSN already does.
"""

from __future__ import annotations

import pytest

import eco_mcp_app.telemetry as telemetry


@pytest.fixture(autouse=True)
def _reset_init_flag():
    """Each test exercises a fresh init; clear the process-wide idempotency latch."""
    telemetry._initialized = False
    yield
    telemetry._initialized = False


def test_malformed_dsn_does_not_crash(monkeypatch):
    """A truthy-but-invalid DSN falls back to a no-op init, never raising."""
    monkeypatch.setenv("SENTRY_DSN", "bare-string-with-no-scheme")
    calls = []

    def fake_init(*args, **kwargs):
        # First call mimics sentry_sdk rejecting the bad DSN; the fallback
        # (no kwargs) must succeed.
        if kwargs.get("dsn"):
            raise telemetry.sentry_sdk.utils.BadDsn("Unsupported scheme ''")
        calls.append(kwargs)

    monkeypatch.setattr(telemetry.sentry_sdk, "init", fake_init)

    telemetry.init_sentry()  # must not raise

    assert calls == [{}], "expected exactly one no-DSN fallback init"
    assert telemetry._initialized is True


def test_unset_dsn_uses_noop_init(monkeypatch):
    """No DSN set -> plain no-op init, unchanged behavior."""
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    calls = []
    monkeypatch.setattr(telemetry.sentry_sdk, "init", lambda *a, **k: calls.append(k))

    telemetry.init_sentry()

    assert calls == [{}]


def test_valid_dsn_initializes_with_integrations(monkeypatch):
    """A valid DSN wires the real client with the DSN passed through."""
    monkeypatch.setenv("SENTRY_DSN", "https://key@o1.ingest.sentry.io/1")
    calls = []
    monkeypatch.setattr(telemetry.sentry_sdk, "init", lambda *a, **k: calls.append(k))

    telemetry.init_sentry()

    assert len(calls) == 1
    assert calls[0]["dsn"] == "https://key@o1.ingest.sentry.io/1"
    assert calls[0]["integrations"]
