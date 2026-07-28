"""Unit tests for eco-app's OpenTelemetry setup."""

from __future__ import annotations

import pytest

import eco_mcp_app.telemetry as telemetry


@pytest.fixture(autouse=True)
def _reset_init_flag():
    telemetry._initialized = False
    telemetry._enabled = False
    yield
    telemetry._initialized = False
    telemetry._enabled = False


def test_unset_endpoint_disables_export(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    assert telemetry.init_telemetry() is False
    assert telemetry._initialized is True


def test_configured_endpoint_builds_http_exporter(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://ser8:30418")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "eco-app-test")
    exporters: list[str] = []

    class FakeExporter:
        def __init__(self, *, endpoint: str):
            exporters.append(endpoint)

    class FakeProvider:
        def __init__(self, *, resource):
            self.resource = resource

        def add_span_processor(self, _processor):
            return None

    monkeypatch.setattr(telemetry, "OTLPSpanExporter", FakeExporter)
    monkeypatch.setattr(telemetry, "TracerProvider", FakeProvider)
    monkeypatch.setattr(telemetry, "BatchSpanProcessor", lambda exporter: exporter)
    monkeypatch.setattr(telemetry.trace, "set_tracer_provider", lambda _provider: None)

    assert telemetry.init_telemetry() is True
    assert exporters == ["http://ser8:30418/v1/traces"]


def test_instrument_asgi_adds_middleware_when_enabled(monkeypatch):
    class FakeApp:
        def __init__(self):
            self.middleware = []

        def add_middleware(self, middleware):
            self.middleware.append(middleware)

    app = FakeApp()
    monkeypatch.setattr(telemetry, "init_telemetry", lambda: True)

    assert telemetry.instrument_asgi(app) is app
    assert app.middleware == [telemetry.OpenTelemetryMiddleware]


def test_record_exception_creates_error_span(monkeypatch):
    statuses = []
    exceptions = []

    class FakeSpan:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def record_exception(self, exc):
            exceptions.append(exc)

        def set_status(self, status):
            statuses.append(status.status_code)

    class FakeTracer:
        def start_as_current_span(self, _operation):
            return FakeSpan()

    error = RuntimeError("boom")
    monkeypatch.setattr(telemetry, "init_telemetry", lambda: True)
    monkeypatch.setattr(telemetry.trace, "get_tracer", lambda _name: FakeTracer())

    telemetry.record_exception(error, "test.operation")

    assert exceptions == [error]
    assert statuses == [telemetry.StatusCode.ERROR]
