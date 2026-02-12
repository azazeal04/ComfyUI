"""NOVA Node ABI v2 scaffolding + v1 adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class NodeExecutionDescriptor:
    supports_streaming: bool = False
    supports_tiling: bool = False
    quantization_support: str = "none"


class NodeABIv2(Protocol):
    @classmethod
    def EXECUTION_DESCRIPTOR(cls) -> NodeExecutionDescriptor: ...


class NodeV1Adapter:
    """Conservative metadata for legacy nodes lacking ABI v2 information."""

    @staticmethod
    def get_execution_descriptor(_legacy_node_cls) -> NodeExecutionDescriptor:
        return NodeExecutionDescriptor(
            supports_streaming=False,
            supports_tiling=False,
            quantization_support="unknown",
        )
