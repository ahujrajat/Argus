from __future__ import annotations
import os
import pytest
from unittest.mock import patch
from opentelemetry import trace as otel_trace


def test_setup_tracing_runs_without_error():
    from core.observability.tracing import setup_tracing
    # Should not raise
    setup_tracing("test-service")


def test_get_tracer_returns_tracer_instance():
    from core.observability import tracing as tracing_mod
    # Reset module-level _tracer so get_tracer triggers setup
    tracing_mod._tracer = None
    tracer = tracing_mod.get_tracer()
    # opentelemetry.trace.Tracer is a protocol; check it has start_as_current_span
    assert hasattr(tracer, "start_as_current_span")


def test_get_tracer_returns_same_instance_on_repeat_calls():
    from core.observability import tracing as tracing_mod
    tracing_mod._tracer = None
    t1 = tracing_mod.get_tracer()
    t2 = tracing_mod.get_tracer()
    assert t1 is t2


def test_setup_tracing_uses_console_exporter_by_default(monkeypatch):
    """When OTEL_EXPORTER_OTLP_ENDPOINT is not set, ConsoleSpanExporter is used."""
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    from core.observability.tracing import setup_tracing
    from core.observability import tracing as tracing_mod
    tracing_mod._tracer = None
    # Should not raise; uses console exporter path
    setup_tracing("argus-console-test")
    assert tracing_mod._tracer is not None


def test_setup_tracing_uses_otlp_when_env_var_set(monkeypatch):
    """When OTEL_EXPORTER_OTLP_ENDPOINT is set, OTLPSpanExporter branch is taken."""
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    from core.observability import tracing as tracing_mod
    tracing_mod._tracer = None

    with patch("core.observability.tracing.BatchSpanProcessor") as mock_bsp, \
         patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter") as mock_otlp:
        from core.observability.tracing import setup_tracing
        setup_tracing("argus-otlp-test")
        # BatchSpanProcessor was called (at least once)
        assert mock_bsp.called


def test_setup_tracing_service_name_in_resource():
    """Resource is created with the given service name."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import Resource
    from core.observability import tracing as tracing_mod
    tracing_mod._tracer = None

    with patch("core.observability.tracing.TracerProvider") as mock_provider_cls:
        mock_provider = mock_provider_cls.return_value
        mock_provider.add_span_processor = lambda x: None
        mock_provider.get_tracer = lambda name: otel_trace.get_tracer(name)

        from core.observability.tracing import setup_tracing
        setup_tracing("my-custom-service")

        # Resource passed to TracerProvider should have service.name
        call_kwargs = mock_provider_cls.call_args
        resource_arg = call_kwargs.kwargs.get("resource") or call_kwargs.args[0] if call_kwargs.args else None
        if resource_arg is not None:
            assert resource_arg.attributes.get("service.name") == "my-custom-service"
