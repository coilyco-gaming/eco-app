"""OpenTelemetry setup for eco-app.

The deploy surface points private workloads at SigNoz's OTLP/HTTP NodePort.
ASGI instrumentation records uncaught exceptions as span events and marks the
request span as an error, which feeds SigNoz Exceptions without a second error
tracking SDK.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode

_log = logging.getLogger(__name__)
_initialized = False
_enabled = False


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
    """Add exception-recording ASGI instrumentation when OTLP is configured."""
    if init_telemetry():
        app.add_middleware(OpenTelemetryMiddleware)
    return app


def record_exception(exc: Exception, operation: str) -> None:
    """Export a fatal non-ASGI exception as a short error span."""
    if not init_telemetry():
        return
    tracer = trace.get_tracer("eco-app")
    with tracer.start_as_current_span(operation) as span:
        span.record_exception(exc)
        span.set_status(Status(StatusCode.ERROR))
