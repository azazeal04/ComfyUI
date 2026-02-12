"""NOVA scheduler façade (phase-in): planning + telemetry + legacy execution path."""

from __future__ import annotations

from typing import Any

from comfy_execution.profile_policy import detect_profile, get_profile_hints
from comfy_execution.residency_graph import ResidencyGraph
from comfy_execution.telemetry import ExecutionTelemetry


class NovaPromptExecutor:
    """Wrapper around legacy PromptExecutor while NOVA scheduler is phased in."""

    def __init__(self, server: Any, cache_type=False, cache_args=None):
        from execution import PromptExecutor  # local import to avoid circular deps

        self._legacy = PromptExecutor(server, cache_type=cache_type, cache_args=cache_args)
        self.server = server
        self.residency = ResidencyGraph()
        self.telemetry = ExecutionTelemetry(server)

    @property
    def history_result(self):
        return self._legacy.history_result

    @property
    def success(self):
        return self._legacy.success

    @property
    def status_messages(self):
        return self._legacy.status_messages

    def reset(self):
        self._legacy.reset()

    def execute(self, prompt, prompt_id, extra_data={}, execute_outputs=[]):
        profile = detect_profile()
        hints = get_profile_hints(profile)
        self.telemetry.emit(
            "telemetry.nova_plan",
            {
                "prompt_id": prompt_id,
                "profile": profile.value,
                "tile_size": hints.tile_size,
                "micro_batch": hints.micro_batch,
                "quantization": hints.quantization,
            },
        )

        # Read-only residency observations for phase 2 bootstrap.
        for node_id in prompt.keys():
            self.residency.touch(f"node:{node_id}")

        self._legacy.execute(prompt, prompt_id, extra_data, execute_outputs)

        self.telemetry.emit(
            "telemetry.nova_residency_snapshot",
            {
                "prompt_id": prompt_id,
                **self.residency.snapshot(),
            },
        )
