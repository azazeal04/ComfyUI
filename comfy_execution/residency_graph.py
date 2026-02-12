"""Read-only residency graph scaffolding for NOVA migration phases."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
import time
from typing import Dict


class AssetState(str, Enum):
    UNLOADED = "unloaded"
    CPU_MMAP = "cpu_mmap"
    CPU_HOT = "cpu_hot"
    GPU_FULL = "gpu_full"
    GPU_PARTIAL = "gpu_partial"


@dataclass
class ResidencyAsset:
    asset_id: str
    state: AssetState = AssetState.UNLOADED
    bytes_total: int = 0
    bytes_gpu_resident: int = 0
    last_used_ts_ms: int = 0
    pin_priority: int = 0


class ResidencyGraph:
    """Lightweight, thread-safe enough for current single worker usage."""

    def __init__(self):
        self._assets: Dict[str, ResidencyAsset] = {}

    def touch(self, asset_id: str, *, state: AssetState | None = None, bytes_total: int | None = None, bytes_gpu_resident: int | None = None) -> None:
        now = int(time.time() * 1000)
        asset = self._assets.get(asset_id)
        if asset is None:
            asset = ResidencyAsset(asset_id=asset_id)
            self._assets[asset_id] = asset
        if state is not None:
            asset.state = state
        if bytes_total is not None:
            asset.bytes_total = bytes_total
        if bytes_gpu_resident is not None:
            asset.bytes_gpu_resident = bytes_gpu_resident
        asset.last_used_ts_ms = now

    def snapshot(self) -> dict:
        return {
            "assets": [asdict(asset) for asset in self._assets.values()],
            "asset_count": len(self._assets),
        }
