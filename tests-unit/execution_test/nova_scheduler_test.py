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
    assert "p1" in server.nova_prompt_plans
    plan = server.nova_prompt_plans["p1"]
    assert plan["image"]["tile_count"] > 0
    assert plan["video"]["window_count"] > 0
    assert plan["audio"]["segment_count"] > 0


def test_nova_executor_emits_video_audio_plan_events(monkeypatch):
    import comfy_execution.nova_scheduler as ns

    monkeypatch.setitem(__import__("sys").modules, "execution", type("M", (), {"PromptExecutor": FakeLegacyExecutor})())
    monkeypatch.setattr(ns, "detect_profile", lambda: __import__("comfy_execution.profile_policy", fromlist=["NovaExecutionProfile"]).NovaExecutionProfile.PASCAL_4G)

    server = FakeServer()
    ex = NovaPromptExecutor(server)
    prompt = {
        "1": {"class_type": "VideoGenerator", "inputs": {"num_frames": 16, "width": 1024, "height": 1024}},
        "2": {"class_type": "AudioGenerator", "inputs": {"sample_count": 96000}},
    }
    ex.execute(prompt, "p2", {}, [])

    event_names = [name for name, _, _ in server.events]
    assert "telemetry.output.partial.video_plan" in event_names
    assert "telemetry.output.partial.audio_plan" in event_names


def test_nova_executor_auto_optimize_path(monkeypatch):
    import comfy_execution.nova_scheduler as ns

    monkeypatch.setitem(__import__("sys").modules, "execution", type("M", (), {"PromptExecutor": FakeLegacyExecutor})())
    monkeypatch.setattr(ns, "detect_profile", lambda: __import__("comfy_execution.profile_policy", fromlist=["NovaExecutionProfile"]).NovaExecutionProfile.PASCAL_2G)

    server = FakeServer()
    ex = NovaPromptExecutor(server)
    prompt = {"1": {"class_type": "KSampler", "inputs": {"width": 2048, "height": 2048, "steps": 60}}}
    ex.execute(prompt, "p3", {"nova_auto_optimize": True}, [])

    event_names = [name for name, _, _ in server.events]
    assert "telemetry.nova_auto_optimized" in event_names
    assert "p3" in server.nova_prompt_plans
    assert server.nova_prompt_plans["p3"]["optimization"]["changed_node_count"] >= 1
