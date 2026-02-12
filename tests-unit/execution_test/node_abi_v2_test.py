from comfy_execution.node_abi_v2 import NodeV1Adapter


class LegacyNode:
    pass


def test_v1_adapter_returns_conservative_descriptor():
    descriptor = NodeV1Adapter.get_execution_descriptor(LegacyNode)
    assert descriptor.supports_streaming is False
    assert descriptor.supports_tiling is False
    assert descriptor.quantization_support == "unknown"
