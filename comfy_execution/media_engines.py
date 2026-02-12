"""Media execution engine interfaces for future NOVA streaming runtime."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EngineChunkPlan:
    chunk_size: int
    overlap: int = 0


class ImageEngine:
    def plan_chunks(self, width: int, height: int, tile_size: int) -> EngineChunkPlan:
        return EngineChunkPlan(chunk_size=min(width, height, tile_size), overlap=32)


class VideoEngine:
    def plan_chunks(self, frame_count: int) -> EngineChunkPlan:
        return EngineChunkPlan(chunk_size=min(frame_count, 8), overlap=2)


class AudioEngine:
    def plan_chunks(self, sample_count: int) -> EngineChunkPlan:
        return EngineChunkPlan(chunk_size=min(sample_count, 48_000), overlap=2_048)
