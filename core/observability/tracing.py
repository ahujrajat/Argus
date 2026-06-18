from __future__ import annotations
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource

_tracer: trace.Tracer | None = None


def setup_tracing(service_name: str = "argus") -> None:
    """Configure SDK. Uses OTLP if OTEL_EXPORTER_OTLP_ENDPOINT is set, else Console."""
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    global _tracer
    _tracer = trace.get_tracer(service_name)


def get_tracer() -> trace.Tracer:
    global _tracer
    if _tracer is None:
        setup_tracing()
    return _tracer
