from comfy_execution.profile_policy import (
    NovaExecutionProfile,
    auto_optimize_hint,
    get_profile_hints,
)


def test_get_profile_hints_pascal_2g_defaults():
    hints = get_profile_hints(NovaExecutionProfile.PASCAL_2G)
    assert hints.profile == NovaExecutionProfile.PASCAL_2G
    assert hints.tile_size == 512
    assert hints.quantization == "int8"


def test_auto_optimize_hint_large_image_reduces_tile():
    out = auto_optimize_hint({"profile": "pascal_4g", "width": 2048, "height": 1536, "steps": 40})
    assert "profile" in out
    assert "recommended" in out
    rec = out["recommended"]
    assert rec["tile_size"] > 0
    assert rec["max_steps"] <= 40
