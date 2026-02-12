"""
Telemetry helpers for NOVA-style execution instrumentation.

This module is intentionally non-invasive: it should never alter execution
behavior. It only emits optional websocket telemetry events when supported by
connected clients.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any

from comfy_api import feature_flags


class ExecutionTelemetry:
    """Small helper for emitting opt-in telemetry events to websocket clients."""

    def __init__(self, server: Any):
        self.server = server

    def _client_supports_telemetry(self) -> bool:
        sid = getattr(self.server, "client_id", None)
        sockets_metadata = getattr(self.server, "sockets_metadata", None)
        if sid is None or sockets_metadata is None:
            return False
        return feature_flags.supports_feature(
            sockets_metadata,
            sid,
            "supports_nova_telemetry",
        )

    def emit(self, event: str, payload: dict[str, Any]) -> None:
        if not self._client_supports_telemetry():
            return
        message = {
            **payload,
            "timestamp": int(time.time() * 1000),
        }
        self.server.send_sync(event, message, self.server.client_id)

    @contextmanager
    def track_duration(self, start_event: str, end_event: str, payload: dict[str, Any]):
        start = time.perf_counter()
        self.emit(start_event, payload)
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self.emit(end_event, {
                **payload,
                "duration_ms": round(elapsed_ms, 3),
            })
