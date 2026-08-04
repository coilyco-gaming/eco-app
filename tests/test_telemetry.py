"""Unit tests for eco-app's OpenTelemetry setup."""

from __future__ import annotations

import logging

import pytest
from mcp import types as mt
from mcp.server.lowlevel import Server
from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

import eco_mcp_app.telemetry as telemetry


@pytest.fixture(autouse=True)
def _reset_init_flag():
    access_logger = logging.getLogger("uvicorn.access")
    original_filters = list(access_logger.filters)
    telemetry._initialized = False
    telemetry._enabled = False
    yield
    telemetry._initialized = False
    telemetry._enabled = False
    access_logger.filters[:] = original_filters


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

        def add_middleware(self, middleware, **kwargs):
            self.middleware.append((middleware, kwargs))

    app = FakeApp()
    monkeypatch.setattr(telemetry, "init_telemetry", lambda: True)

    assert telemetry.instrument_asgi(app) is app
    assert app.middleware == [
        (
            telemetry.OpenTelemetryMiddleware,
            {
                "excluded_urls": r"/healthz$",
                "exclude_spans": ["receive", "send"],
            },
        )
    ]


def test_healthcheck_access_filter_is_exact() -> None:
    access_filter = telemetry._HealthcheckAccessFilter()

    def record(path: str) -> logging.LogRecord:
        return logging.LogRecord(
            "uvicorn.access",
            logging.INFO,
            __file__,
            1,
            '%s - "%s %s HTTP/%s" %d',
            ("127.0.0.1:1234", "GET", path, "1.1", 200),
            None,
        )

    assert access_filter.filter(record("/healthz")) is False
    assert access_filter.filter(record("/healthz?probe=1")) is False
    assert access_filter.filter(record("/healthz/details")) is True
    assert access_filter.filter(record("/api/service")) is True


def test_asgi_instrumentation_exports_api_span_but_not_health(monkeypatch) -> None:
    async def ok(_request):
        return JSONResponse({"ok": True})

    exporter = InMemorySpanExporter()
    provider = SdkTracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "init_telemetry", lambda: True)
    monkeypatch.setattr(
        telemetry.trace,
        "get_tracer",
        lambda name, version=None, tracer_provider=None, schema_url=None: provider.get_tracer(
            name, version, schema_url
        ),
    )
    app = Starlette(
        routes=[
            Route("/healthz", ok),
            Route("/api/example", ok),
        ]
    )
    telemetry.instrument_asgi(app)

    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/api/example").status_code == 200

    spans = exporter.get_finished_spans()
    assert [span.name for span in spans] == ["GET /api/example"]


@pytest.mark.asyncio
async def test_mcp_tool_instrumentation_uses_semantic_server_span(monkeypatch) -> None:
    exporter = InMemorySpanExporter()
    provider = SdkTracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    transport_tracer = provider.get_tracer("test-transport")

    async def handler(_request):
        return mt.ServerResult(mt.CallToolResult(content=[], isError=False))

    server = Server("test-telemetry")
    server.request_handlers[mt.CallToolRequest] = handler
    monkeypatch.setattr(telemetry, "init_telemetry", lambda: True)
    monkeypatch.setattr(
        telemetry.trace,
        "get_tracer",
        lambda name, *_args, **_kwargs: provider.get_tracer(name),
    )
    telemetry.instrument_mcp_server(server)
    telemetry.instrument_mcp_server(server)

    request = mt.CallToolRequest(
        method="tools/call",
        params=mt.CallToolRequestParams(name="get_server_status", arguments={}),
    )
    with transport_tracer.start_as_current_span("POST /mcp/") as transport_span:
        transport_context = transport_span.get_span_context()
        await server.request_handlers[mt.CallToolRequest](request)

    spans = exporter.get_finished_spans()
    tool_spans = [span for span in spans if span.name == "tools/call get_server_status"]
    assert len(tool_spans) == 1
    span = tool_spans[0]
    assert span.name == "tools/call get_server_status"
    assert span.kind is telemetry.SpanKind.SERVER
    assert dict(span.attributes or {}) == {
        "mcp.method.name": "tools/call",
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.tool.name": "get_server_status",
    }
    assert span.parent is None
    assert [link.context.span_id for link in span.links] == [transport_context.span_id]
    assert span.status.status_code is telemetry.StatusCode.UNSET


@pytest.mark.asyncio
async def test_mcp_tool_error_marks_span(monkeypatch) -> None:
    exporter = InMemorySpanExporter()
    provider = SdkTracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    async def handler(_request):
        return mt.ServerResult(mt.CallToolResult(content=[], isError=True))

    server = Server("test-telemetry")
    server.request_handlers[mt.CallToolRequest] = handler
    monkeypatch.setattr(telemetry, "init_telemetry", lambda: True)
    monkeypatch.setattr(
        telemetry.trace,
        "get_tracer",
        lambda name, *_args, **_kwargs: provider.get_tracer(name),
    )
    telemetry.instrument_mcp_server(server)
    request = mt.CallToolRequest(
        method="tools/call",
        params=mt.CallToolRequestParams(name="get_server_status", arguments={}),
    )

    await server.request_handlers[mt.CallToolRequest](request)

    (span,) = exporter.get_finished_spans()
    assert span.attributes is not None
    assert span.attributes["error.type"] == "tool_error"
    assert span.status.status_code is telemetry.StatusCode.ERROR


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
