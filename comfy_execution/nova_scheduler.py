"""NOVA scheduler façade (phase-in): planning + telemetry + legacy execution path."""

from __future__ import annotations

from typing import Any

from comfy_execution.media_engines import AudioEngine, ImageEngine, VideoEngine
from comfy_execution.profile_policy import detect_profile, get_profile_hints, optimize_prompt_graph
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
        self.image_engine = ImageEngine()
        self.video_engine = VideoEngine()
        self.audio_engine = AudioEngine()

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

    def _infer_dimensions(self, prompt: dict) -> tuple[int, int]:
        for node in prompt.values():
            inputs = node.get("inputs", {})
            width = inputs.get("width")
            height = inputs.get("height")
            if isinstance(width, int) and isinstance(height, int):
                return max(64, width), max(64, height)
        return (1024, 1024)

    def _infer_video_frames(self, prompt: dict) -> int:
        for node in prompt.values():
            inputs = node.get("inputs", {})
            for key in ("frames", "num_frames", "frame_count"):
                value = inputs.get(key)
                if isinstance(value, int) and value > 0:
                    return value
        return 24

    def _infer_audio_samples(self, prompt: dict) -> int:
        for node in prompt.values():
            inputs = node.get("inputs", {})
            sample_count = inputs.get("sample_count")
            if isinstance(sample_count, int) and sample_count > 0:
                return sample_count
            seconds = inputs.get("seconds")
            sample_rate = inputs.get("sample_rate")
            if isinstance(seconds, (int, float)) and isinstance(sample_rate, int) and sample_rate > 0:
                return int(seconds * sample_rate)
        return 48_000 * 8

    def _contains_keyword_node(self, prompt: dict, keywords: tuple[str, ...]) -> bool:
        for node in prompt.values():
            class_type = str(node.get("class_type", "")).lower()
            if any(keyword in class_type for keyword in keywords):
                return True
        return False

    def _build_stream_plan(self, prompt: dict, tile_size: int) -> dict:
        width, height = self._infer_dimensions(prompt)
        image_tiles = self.image_engine.plan_tiles(width, height, tile_size)
        video_windows = self.video_engine.plan_windows(self._infer_video_frames(prompt))
        audio_segments = self.audio_engine.plan_segments(self._infer_audio_samples(prompt))

        plan = {
            "image": {
                "enabled": self._contains_keyword_node(prompt, ("ksampler", "sampler", "image", "latent")),
                "width": width,
                "height": height,
                "tile_size": tile_size,
                "tiles": [tile.__dict__ for tile in image_tiles],
                "tile_count": len(image_tiles),
            },
            "video": {
                "enabled": self._contains_keyword_node(prompt, ("video", "frame")),
                "windows": [{"start": start, "end": end} for (start, end) in video_windows],
                "window_count": len(video_windows),
            },
            "audio": {
                "enabled": self._contains_keyword_node(prompt, ("audio", "music", "spectrogram")),
                "segments": [{"start": start, "end": end} for (start, end) in audio_segments],
                "segment_count": len(audio_segments),
            },
        }
        return plan

    def execute(self, prompt, prompt_id, extra_data={}, execute_outputs=[]):
        profile = detect_profile()
        hints = get_profile_hints(profile)

        optimized_prompt = prompt
        optimization_summary = {"changed_node_count": 0, "changed_nodes": {}}
        if extra_data.get("nova_auto_optimize", False):
            optimized_prompt, optimization_summary = optimize_prompt_graph(prompt, hints)
            self.telemetry.emit("telemetry.nova_auto_optimized", {
                "prompt_id": prompt_id,
                "changed_node_count": optimization_summary.get("changed_node_count", 0),
            })

        stream_plan = self._build_stream_plan(optimized_prompt, hints.tile_size)

        if not hasattr(self.server, "nova_prompt_plans"):
            self.server.nova_prompt_plans = {}
        stream_plan["optimization"] = optimization_summary
        self.server.nova_prompt_plans[prompt_id] = stream_plan

        self.telemetry.emit(
            "telemetry.nova_plan",
            {
                "prompt_id": prompt_id,
                "profile": profile.value,
                "tile_size": hints.tile_size,
                "micro_batch": hints.micro_batch,
                "quantization": hints.quantization,
                "image_tile_count": stream_plan["image"]["tile_count"],
                "video_window_count": stream_plan["video"]["window_count"],
                "audio_segment_count": stream_plan["audio"]["segment_count"],
                "optimized": optimization_summary.get("changed_node_count", 0) > 0,
            },
        )

        # Read-only residency observations for phase 2 bootstrap.
        for node_id in optimized_prompt.keys():
            self.residency.touch(f"node:{node_id}")

        if stream_plan["video"]["enabled"]:
            self.telemetry.emit("telemetry.output.partial.video_plan", {
                "prompt_id": prompt_id,
                "windows": stream_plan["video"]["windows"],
            })
        if stream_plan["audio"]["enabled"]:
            self.telemetry.emit("telemetry.output.partial.audio_plan", {
                "prompt_id": prompt_id,
                "segments": stream_plan["audio"]["segments"],
            })

        self._legacy.execute(optimized_prompt, prompt_id, extra_data, execute_outputs)

        self.telemetry.emit(
            "telemetry.nova_residency_snapshot",
            {
                "prompt_id": prompt_id,
                **self.residency.snapshot(),
            },
        )
