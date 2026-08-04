"""OpenTelemetry setup for eco-app.

The deploy surface points private workloads at SigNoz's OTLP/HTTP NodePort.
ASGI instrumentation records uncaught exceptions as span events and marks the
request span as an error, which feeds SigNoz Exceptions without a second error
tracking SDK.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any, cast

from mcp import types as mt
from mcp.server.lowlevel import Server
from opentelemetry import metrics, propagate, trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.metrics import Counter as ApiCounter
from opentelemetry.sdk.metrics import Counter, Histogram, MeterProvider
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Link, SpanKind, Status, StatusCode

_log = logging.getLogger(__name__)
_initialized = False
_enabled = False
_trace_provider: TracerProvider | None = None
_meter_provider: MeterProvider | None = None
_mcp_tool_calls: ApiCounter | None = None
_HEALTHCHECK_PATH = "/healthz"
_MCP_HANDLER_MARKER = "_eco_app_mcp_traced"
_ACTIVITY_METRIC_TEMPORALITY: dict[type, AggregationTemporality] = {
    Counter: AggregationTemporality.DELTA,
    Histogram: AggregationTemporality.DELTA,
}


class _HealthcheckAccessFilter(logging.Filter):
    """Drop only Uvicorn access records for the exact healthcheck path."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3:
            path = str(args[2]).partition("?")[0]
            return path != _HEALTHCHECK_PATH
        return True


def configure_healthcheck_logging() -> None:
    """Keep Kubernetes probes out of the web server's access log."""
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, _HealthcheckAccessFilter) for item in access_logger.filters):
        access_logger.addFilter(_HealthcheckAccessFilter())


def init_telemetry() -> bool:
    """Configure OTLP tracing and metrics once and report whether either is enabled."""
    global _enabled, _initialized, _mcp_tool_calls, _meter_provider, _trace_provider
    if _initialized:
        return _enabled

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    service_name = os.getenv("OTEL_SERVICE_NAME", "eco-app").strip() or "eco-app"
    if not endpoint:
        _initialized = True
        return False

    try:
        resource = Resource.create(
            {
                "service.name": service_name,
                "deployment.environment": os.getenv("OTEL_DEPLOYMENT_ENVIRONMENT", "homelab"),
            }
        )
    except Exception:
        _log.warning("OpenTelemetry resource initialization failed; continuing", exc_info=True)
        _initialized = True
        return False

    try:
        trace_provider = TracerProvider(resource=resource)
        trace_exporter = OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")
        trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
        trace.set_tracer_provider(trace_provider)
    except Exception:
        _log.warning(
            "OpenTelemetry trace initialization failed; continuing without trace export",
            exc_info=True,
        )
    else:
        _trace_provider = trace_provider

    try:
        metric_exporter = OTLPMetricExporter(
            endpoint=f"{endpoint.rstrip('/')}/v1/metrics",
            preferred_temporality=_ACTIVITY_METRIC_TEMPORALITY,
        )
        metric_reader = PeriodicExportingMetricReader(metric_exporter)
        meter_provider = MeterProvider(metric_readers=[metric_reader], resource=resource)
        metrics.set_meter_provider(meter_provider)
    except Exception:
        _log.warning(
            "OpenTelemetry metric initialization failed; continuing without metric export",
            exc_info=True,
        )
    else:
        _meter_provider = meter_provider
        try:
            _mcp_tool_calls = meter_provider.get_meter("eco-app").create_counter(
                "eco_app.mcp.tool.calls",
                unit="{call}",
                description="Number of MCP tool calls handled by eco-app.",
            )
        except Exception:
            _log.warning(
                "OpenTelemetry MCP counter initialization failed; continuing with HTTP metrics",
                exc_info=True,
            )

    _enabled = _trace_provider is not None or _meter_provider is not None
    _initialized = True
    return _enabled


def instrument_asgi(app: Any) -> Any:
    """Trace every non-health ASGI request and suppress health access logs."""
    configure_healthcheck_logging()
    if init_telemetry():
        app.add_middleware(
            OpenTelemetryMiddleware,
            excluded_urls=rf"{_HEALTHCHECK_PATH}$",
            exclude_spans=["receive", "send"],
            tracer_provider=_trace_provider,
            meter_provider=_meter_provider,
        )
    return app


def _record_mcp_tool_call(tool_name: str, outcome: str) -> None:
    """Record one bounded MCP call without letting telemetry break the tool."""
    if _mcp_tool_calls is None:
        return
    try:
        _mcp_tool_calls.add(
            1,
            {
                "gen_ai.tool.name": tool_name,
                "mcp.tool.outcome": outcome,
            },
        )
    except Exception:
        _log.warning("OpenTelemetry MCP call metric failed", exc_info=True)


def instrument_mcp_server(server: Server) -> Server:
    """Give every MCP tool call one semantic server span across all transports."""
    handler = server.request_handlers.get(mt.CallToolRequest)
    if handler is None:
        raise RuntimeError("MCP tool instrumentation requires a registered call-tool handler")
    if getattr(handler, _MCP_HANDLER_MARKER, False):
        return server

    original = cast(
        Callable[[mt.CallToolRequest], Awaitable[mt.ServerResult]],
        handler,
    )

    async def traced_call_tool(request: mt.CallToolRequest) -> mt.ServerResult:
        if not init_telemetry():
            return await original(request)

        tool_name = request.params.name
        carrier: dict[str, str] = {}
        if request.params.meta is not None:
            metadata = request.params.meta.model_dump(exclude_none=True)
            for key in ("traceparent", "tracestate", "baggage"):
                value = metadata.get(key)
                if isinstance(value, str):
                    carrier[key] = value
        # MCP context travels in params._meta independently from its transport.
        # Start at an empty root and link any ambient HTTP span instead of
        # making the logical tool operation an ordinary child of that request.
        parent_context = propagate.extract(carrier, context=Context())
        ambient_context = trace.get_current_span().get_span_context()
        links = [Link(ambient_context)] if ambient_context.is_valid else None
        tracer = trace.get_tracer("eco-app")
        with tracer.start_as_current_span(
            f"tools/call {tool_name}",
            context=parent_context,
            kind=SpanKind.SERVER,
            attributes={
                "mcp.method.name": "tools/call",
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": tool_name,
            },
            links=links,
        ) as span:
            try:
                result = await original(request)
            except Exception as exc:
                error_type = f"{type(exc).__module__}.{type(exc).__qualname__}"
                span.set_attribute("error.type", error_type)
                span.set_status(Status(StatusCode.ERROR))
                _record_mcp_tool_call(tool_name, "exception")
                raise
            if isinstance(result.root, mt.CallToolResult) and result.root.isError:
                span.set_attribute("error.type", "tool_error")
                span.set_status(Status(StatusCode.ERROR))
                _record_mcp_tool_call(tool_name, "tool_error")
            else:
                _record_mcp_tool_call(tool_name, "success")
            return result

    setattr(traced_call_tool, _MCP_HANDLER_MARKER, True)
    server.request_handlers[mt.CallToolRequest] = traced_call_tool
    return server


def record_exception(exc: Exception, operation: str) -> None:
    """Export a fatal non-ASGI exception as a short error span."""
    if not init_telemetry():
        return
    tracer = trace.get_tracer("eco-app")
    with tracer.start_as_current_span(operation) as span:
        span.record_exception(exc)
        span.set_status(Status(StatusCode.ERROR))
