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
from opentelemetry import propagate, trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Link, SpanKind, Status, StatusCode

_log = logging.getLogger(__name__)
_initialized = False
_enabled = False
_HEALTHCHECK_PATH = "/healthz"
_MCP_HANDLER_MARKER = "_eco_app_mcp_traced"


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
    """Configure OTLP tracing once and report whether export is enabled."""
    global _enabled, _initialized
    if _initialized:
        return _enabled

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    service_name = os.getenv("OTEL_SERVICE_NAME", "eco-app").strip() or "eco-app"
    if not endpoint:
        _initialized = True
        return False

    try:
        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": service_name,
                    "deployment.environment": os.getenv("OTEL_DEPLOYMENT_ENVIRONMENT", "homelab"),
                }
            )
        )
        exporter = OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces")
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
    except Exception:
        _log.warning(
            "OpenTelemetry initialization failed; continuing without trace export",
            exc_info=True,
        )
    else:
        _enabled = True

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
        )
    return app


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
                raise
            if isinstance(result.root, mt.CallToolResult) and result.root.isError:
                span.set_attribute("error.type", "tool_error")
                span.set_status(Status(StatusCode.ERROR))
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
