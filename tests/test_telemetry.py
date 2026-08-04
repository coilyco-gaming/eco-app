"""Unit tests for eco-app's OpenTelemetry setup."""

from __future__ import annotations

import logging

import pytest
from mcp import types as mt
from mcp.server.lowlevel import Server
from opentelemetry.sdk.metrics import Counter as SdkCounter
from opentelemetry.sdk.metrics import MeterProvider as SdkMeterProvider
from opentelemetry.sdk.metrics.export import AggregationTemporality, InMemoryMetricReader
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
    telemetry._trace_provider = None
    telemetry._meter_provider = None
    telemetry._mcp_tool_calls = None
    yield
    telemetry._initialized = False
    telemetry._enabled = False
    telemetry._trace_provider = None
    telemetry._meter_provider = None
    telemetry._mcp_tool_calls = None
    access_logger.filters[:] = original_filters


def test_unset_endpoint_disables_export(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    assert telemetry.init_telemetry() is False
    assert telemetry._initialized is True


def test_configured_endpoint_builds_http_exporter(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://ser8:30418")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "eco-app-test")
    trace_exporters: list[str] = []
    metric_exporters: list[tuple[str, dict[type, AggregationTemporality]]] = []

    class FakeTraceExporter:
        def __init__(self, *, endpoint: str):
            trace_exporters.append(endpoint)

    class FakeTraceProvider:
        def __init__(self, *, resource):
            self.resource = resource

        def add_span_processor(self, _processor):
            return None

    class FakeMetricExporter:
        def __init__(
            self,
            *,
            endpoint: str,
            preferred_temporality: dict[type, AggregationTemporality],
        ):
            metric_exporters.append((endpoint, preferred_temporality))

    class FakeMetricReader:
        def __init__(self, exporter):
            self.exporter = exporter

    class FakeCounter:
        def add(self, _value, _attributes):
            return None

    class FakeMeter:
        def create_counter(self, _name, *, unit, description):
            assert unit == "{call}"
            assert description
            return FakeCounter()

    class FakeMeterProvider:
        def __init__(self, *, metric_readers, resource):
            self.metric_readers = metric_readers
            self.resource = resource

        def get_meter(self, _name):
            return FakeMeter()

    monkeypatch.setattr(telemetry, "OTLPSpanExporter", FakeTraceExporter)
    monkeypatch.setattr(telemetry, "TracerProvider", FakeTraceProvider)
    monkeypatch.setattr(telemetry, "BatchSpanProcessor", lambda exporter: exporter)
    monkeypatch.setattr(telemetry.trace, "set_tracer_provider", lambda _provider: None)
    monkeypatch.setattr(telemetry, "OTLPMetricExporter", FakeMetricExporter)
    monkeypatch.setattr(telemetry, "PeriodicExportingMetricReader", FakeMetricReader)
    monkeypatch.setattr(telemetry, "MeterProvider", FakeMeterProvider)
    monkeypatch.setattr(telemetry.metrics, "set_meter_provider", lambda _provider: None)

    assert telemetry.init_telemetry() is True
    assert trace_exporters == ["http://ser8:30418/v1/traces"]
    assert metric_exporters == [
        (
            "http://ser8:30418/v1/metrics",
            telemetry._ACTIVITY_METRIC_TEMPORALITY,
        )
    ]
    assert telemetry._trace_provider is not None
    assert telemetry._meter_provider is not None
    assert telemetry._mcp_tool_calls is not None


def test_delta_counter_exports_the_first_event() -> None:
    metric_reader = InMemoryMetricReader(
        preferred_temporality={SdkCounter: AggregationTemporality.DELTA}
    )
    meter_provider = SdkMeterProvider(metric_readers=[metric_reader])
    counter = meter_provider.get_meter("eco-app-test").create_counter("first.event")

    counter.add(1, {"kind": "first"})

    metrics_data = metric_reader.get_metrics_data()
    assert metrics_data is not None
    metric = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0]
    assert metric.data.aggregation_temporality is AggregationTemporality.DELTA
    assert [point.value for point in metric.data.data_points] == [1]


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
                "tracer_provider": None,
                "meter_provider": None,
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
    trace_provider = SdkTracerProvider()
    trace_provider.add_span_processor(SimpleSpanProcessor(exporter))
    metric_reader = InMemoryMetricReader()
    meter_provider = SdkMeterProvider(metric_readers=[metric_reader])
    telemetry._trace_provider = trace_provider
    telemetry._meter_provider = meter_provider
    monkeypatch.setattr(telemetry, "init_telemetry", lambda: True)
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
    metrics_data = metric_reader.get_metrics_data()
    assert metrics_data is not None
    request_points = [
        point
        for resource_metrics in metrics_data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
        if metric.name in {"http.server.request.duration", "http.server.duration"}
        for point in metric.data.data_points
    ]
    request_count = 0
    for point in request_points:
        request_count += int(point.count)
    assert request_count == 1
    assert {
        point.attributes.get("http.request.method") or point.attributes.get("http.method")
        for point in request_points
    } == {"GET"}
    assert {
        point.attributes.get("http.response.status_code")
        or point.attributes.get("http.status_code")
        for point in request_points
    } == {200}


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
    metric_calls = []

    class FakeCounter:
        def add(self, value, attributes):
            metric_calls.append((value, attributes))

    monkeypatch.setattr(telemetry, "_mcp_tool_calls", FakeCounter())
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
    assert metric_calls == [
        (
            1,
            {
                "gen_ai.tool.name": "get_server_status",
                "mcp.tool.outcome": "success",
            },
        )
    ]


@pytest.mark.asyncio
async def test_mcp_tool_error_marks_span(monkeypatch) -> None:
    exporter = InMemorySpanExporter()
    provider = SdkTracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    async def handler(_request):
        return mt.ServerResult(mt.CallToolResult(content=[], isError=True))

    server = Server("test-telemetry")
    server.request_handlers[mt.CallToolRequest] = handler
    metric_calls = []

    class FakeCounter:
        def add(self, value, attributes):
            metric_calls.append((value, attributes))

    monkeypatch.setattr(telemetry, "_mcp_tool_calls", FakeCounter())
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
    assert metric_calls == [
        (
            1,
            {
                "gen_ai.tool.name": "get_server_status",
                "mcp.tool.outcome": "tool_error",
            },
        )
    ]


@pytest.mark.asyncio
async def test_mcp_exception_records_exception_metric(monkeypatch) -> None:
    exporter = InMemorySpanExporter()
    provider = SdkTracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    metric_calls = []

    async def handler(_request):
        raise RuntimeError("boom")

    class FakeCounter:
        def add(self, value, attributes):
            metric_calls.append((value, attributes))

    server = Server("test-telemetry")
    server.request_handlers[mt.CallToolRequest] = handler
    monkeypatch.setattr(telemetry, "_mcp_tool_calls", FakeCounter())
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

    with pytest.raises(RuntimeError, match="boom"):
        await server.request_handlers[mt.CallToolRequest](request)

    (span,) = exporter.get_finished_spans()
    assert span.status.status_code is telemetry.StatusCode.ERROR
    assert metric_calls == [
        (
            1,
            {
                "gen_ai.tool.name": "get_server_status",
                "mcp.tool.outcome": "exception",
            },
        )
    ]


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
