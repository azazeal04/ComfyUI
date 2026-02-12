"""NOVA execution profile selection and optimization hints."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import Enum
from typing import Any


class NovaExecutionProfile(str, Enum):
    PASCAL_2G = "pascal_2g"
    PASCAL_4G = "pascal_4g"
    PASCAL_6G_8G = "pascal_6g_8g"
    RTX_MODERN = "rtx_modern"
    AMD_ROCM = "amd_rocm"
    INTEL_XPU = "intel_xpu"
    CPU_SAFE = "cpu_safe"


@dataclass(frozen=True)
class ProfileHints:
    profile: NovaExecutionProfile
    tile_size: int
    micro_batch: int
    quantization: str
    memory_headroom_mb: int


def _gpu_name() -> str:
    import comfy.model_management
    try:
        return comfy.model_management.get_torch_device_name(comfy.model_management.get_torch_device()).lower()
    except Exception:
        return ""


def detect_profile() -> NovaExecutionProfile:
    """Detect an execution profile from runtime device capabilities."""
    import comfy.model_management
    device = comfy.model_management.get_torch_device()
    if hasattr(device, "type") and device.type == "cpu":
        return NovaExecutionProfile.CPU_SAFE

    if comfy.model_management.is_intel_xpu():
        return NovaExecutionProfile.INTEL_XPU
    if comfy.model_management.is_ascend_npu() or comfy.model_management.is_mlu():
        return NovaExecutionProfile.CPU_SAFE

    if "amd" in _gpu_name() or "radeon" in _gpu_name():
        return NovaExecutionProfile.AMD_ROCM

    total_vram_mb = int(getattr(comfy.model_management, "total_vram", 0) or 0)
    if "rtx" in _gpu_name():
        return NovaExecutionProfile.RTX_MODERN
    if total_vram_mb <= 2500:
        return NovaExecutionProfile.PASCAL_2G
    if total_vram_mb <= 4500:
        return NovaExecutionProfile.PASCAL_4G
    if total_vram_mb <= 9000:
        return NovaExecutionProfile.PASCAL_6G_8G
    return NovaExecutionProfile.RTX_MODERN


def get_profile_hints(profile: NovaExecutionProfile | None = None) -> ProfileHints:
    if profile is None:
        profile = detect_profile()

    hints_by_profile = {
        NovaExecutionProfile.PASCAL_2G: ProfileHints(profile, tile_size=512, micro_batch=1, quantization="int8", memory_headroom_mb=512),
        NovaExecutionProfile.PASCAL_4G: ProfileHints(profile, tile_size=768, micro_batch=1, quantization="int8", memory_headroom_mb=768),
        NovaExecutionProfile.PASCAL_6G_8G: ProfileHints(profile, tile_size=1024, micro_batch=1, quantization="int4_or_int8", memory_headroom_mb=1024),
        NovaExecutionProfile.RTX_MODERN: ProfileHints(profile, tile_size=1280, micro_batch=2, quantization="fp16", memory_headroom_mb=1536),
        NovaExecutionProfile.AMD_ROCM: ProfileHints(profile, tile_size=1024, micro_batch=1, quantization="fp16", memory_headroom_mb=1024),
        NovaExecutionProfile.INTEL_XPU: ProfileHints(profile, tile_size=896, micro_batch=1, quantization="fp16", memory_headroom_mb=1024),
        NovaExecutionProfile.CPU_SAFE: ProfileHints(profile, tile_size=512, micro_batch=1, quantization="fp32", memory_headroom_mb=0),
    }
    return hints_by_profile[profile]


def _compute_recommendation(width: int, height: int, steps: int, hints: ProfileHints) -> dict[str, int | str]:
    megapixels = (width * height) / 1_000_000.0
    recommended_tile = hints.tile_size
    if megapixels > 2.5:
        recommended_tile = max(384, hints.tile_size // 2)

    max_steps = min(steps, 28 if "pascal" in hints.profile.value else 40)
    return {
        "tile_size": recommended_tile,
        "micro_batch": hints.micro_batch,
        "quantization": hints.quantization,
        "memory_headroom_mb": hints.memory_headroom_mb,
        "max_steps": max_steps,
    }


def auto_optimize_hint(payload: dict[str, Any]) -> dict[str, Any]:
    """Return frontend-consumable optimization hints without changing runtime behavior."""
    profile_value = payload.get("profile")
    profile = None
    if isinstance(profile_value, str):
        try:
            profile = NovaExecutionProfile(profile_value)
        except ValueError:
            profile = None
    hints = get_profile_hints(profile)
    width = int(payload.get("width", 1024))
    height = int(payload.get("height", 1024))
    steps = int(payload.get("steps", 20))

    return {
        "profile": hints.profile.value,
        "recommended": _compute_recommendation(width, height, steps, hints),
    }


def optimize_prompt_graph(prompt: dict[str, Any], hints: ProfileHints) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create an optimized prompt copy based on profile hints and return changes summary."""
    optimized = copy.deepcopy(prompt)
    changed_nodes: dict[str, dict[str, Any]] = {}

    for node_id, node in optimized.items():
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        before: dict[str, Any] = {}
        after: dict[str, Any] = {}

        width = inputs.get("width")
        height = inputs.get("height")
        steps = inputs.get("steps")

        if isinstance(width, int) and width > hints.tile_size * 2:
            before["width"] = width
            inputs["width"] = hints.tile_size * 2
            after["width"] = inputs["width"]

        if isinstance(height, int) and height > hints.tile_size * 2:
            before["height"] = height
            inputs["height"] = hints.tile_size * 2
            after["height"] = inputs["height"]

        if isinstance(steps, int):
            max_steps = 28 if "pascal" in hints.profile.value else 40
            if steps > max_steps:
                before["steps"] = steps
                inputs["steps"] = max_steps
                after["steps"] = inputs["steps"]

        if before:
            changed_nodes[node_id] = {
                "before": before,
                "after": after,
            }

    return optimized, {
        "changed_nodes": changed_nodes,
        "changed_node_count": len(changed_nodes),
    }
