from comfy_execution.nova_scheduler import NovaPromptExecutor


class FakeLegacyExecutor:
    def __init__(self, server, cache_type=False, cache_args=None):
        self.server = server
        self.success = True
        self.status_messages = []
        self.history_result = {"outputs": {}, "meta": {}}

    def reset(self):
        pass

    def execute(self, prompt, prompt_id, extra_data=None, execute_outputs=None):
        self.status_messages.append(("execution_start", {"prompt_id": prompt_id}))


class FakeServer:
    def __init__(self):
        self.client_id = "sid"
        self.sockets_metadata = {
            "sid": {"feature_flags": {"supports_nova_telemetry": True}}
        }
        self.events = []

    def send_sync(self, event, data, sid=None):
        self.events.append((event, data, sid))


def test_nova_executor_emits_plan_and_snapshot(monkeypatch):
    import comfy_execution.nova_scheduler as ns

    monkeypatch.setitem(__import__("sys").modules, "execution", type("M", (), {"PromptExecutor": FakeLegacyExecutor})())
    monkeypatch.setattr(ns, "detect_profile", lambda: __import__("comfy_execution.profile_policy", fromlist=["NovaExecutionProfile"]).NovaExecutionProfile.PASCAL_4G)

    server = FakeServer()
    ex = NovaPromptExecutor(server)
    ex.execute({"1": {"class_type": "Any", "inputs": {}}}, "p1", {}, [])

    event_names = [name for name, _, _ in server.events]
    assert "telemetry.nova_plan" in event_names
    assert "telemetry.nova_residency_snapshot" in event_names
