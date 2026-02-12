"""Media execution engine helpers for NOVA phased streaming runtime."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EngineChunkPlan:
    chunk_size: int
    overlap: int = 0


@dataclass(frozen=True)
class ImageTile:
    x: int
    y: int
    width: int
    height: int


class ImageEngine:
    def plan_chunks(self, width: int, height: int, tile_size: int) -> EngineChunkPlan:
        return EngineChunkPlan(chunk_size=max(128, min(width, height, tile_size)), overlap=32)

    def plan_tiles(self, width: int, height: int, tile_size: int) -> list[ImageTile]:
        plan = self.plan_chunks(width, height, tile_size)
        step = max(1, plan.chunk_size - plan.overlap)
        tiles: list[ImageTile] = []
        y = 0
        while y < height:
            x = 0
            while x < width:
                w = min(plan.chunk_size, width - x)
                h = min(plan.chunk_size, height - y)
                tiles.append(ImageTile(x=x, y=y, width=w, height=h))
                x += step
            y += step
        return tiles


class VideoEngine:
    def plan_chunks(self, frame_count: int) -> EngineChunkPlan:
        return EngineChunkPlan(chunk_size=max(1, min(frame_count, 8)), overlap=2)

    def plan_windows(self, frame_count: int) -> list[tuple[int, int]]:
        plan = self.plan_chunks(frame_count)
        windows: list[tuple[int, int]] = []
        start = 0
        stride = max(1, plan.chunk_size - plan.overlap)
        while start < frame_count:
            end = min(frame_count, start + plan.chunk_size)
            windows.append((start, end))
            start += stride
        return windows


class AudioEngine:
    def plan_chunks(self, sample_count: int) -> EngineChunkPlan:
        return EngineChunkPlan(chunk_size=max(4096, min(sample_count, 48_000)), overlap=2_048)

    def plan_segments(self, sample_count: int) -> list[tuple[int, int]]:
        plan = self.plan_chunks(sample_count)
        segments: list[tuple[int, int]] = []
        start = 0
        stride = max(1, plan.chunk_size - plan.overlap)
        while start < sample_count:
            end = min(sample_count, start + plan.chunk_size)
            segments.append((start, end))
            start += stride
        return segments
