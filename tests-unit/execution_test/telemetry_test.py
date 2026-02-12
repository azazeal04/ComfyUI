from comfy_execution.telemetry import ExecutionTelemetry


class FakeServer:
    def __init__(self, supports=True):
        self.client_id = "sid-1"
        self.sockets_metadata = {
            self.client_id: {
                "feature_flags": {
                    "supports_nova_telemetry": supports,
                }
            }
        }
        self.messages = []

    def send_sync(self, event, data, sid=None):
        self.messages.append((event, data, sid))


def test_emit_only_when_feature_enabled():
    enabled = FakeServer(supports=True)
    disabled = FakeServer(supports=False)

    ExecutionTelemetry(enabled).emit("telemetry.node_start", {"prompt_id": "p1"})
    ExecutionTelemetry(disabled).emit("telemetry.node_start", {"prompt_id": "p2"})

    assert len(enabled.messages) == 1
    assert enabled.messages[0][0] == "telemetry.node_start"
    assert enabled.messages[0][2] == enabled.client_id
    assert "timestamp" in enabled.messages[0][1]

    assert len(disabled.messages) == 0


def test_track_duration_emits_start_and_end():
    server = FakeServer(supports=True)
    telemetry = ExecutionTelemetry(server)

    with telemetry.track_duration(
        "telemetry.execution_start",
        "telemetry.execution_end",
        {"prompt_id": "p3"},
    ):
        pass

    assert [event for event, _, _ in server.messages] == [
        "telemetry.execution_start",
        "telemetry.execution_end",
    ]
    end_data = server.messages[1][1]
    assert "duration_ms" in end_data
    assert end_data["duration_ms"] >= 0
