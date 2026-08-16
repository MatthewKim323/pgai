"""Dashboard API: call listing, recording serving, traversal guard."""

import json

from starlette.testclient import TestClient

from caller import store
from caller.dashboard import create_dashboard_app
from caller.turnstate import TurnStateMachine


def seed_call(tmp_path, scenario="refill", with_recording=False, findings=None):
    call_dir = store.create_call_dir(scenario, tmp_path)
    m = TurnStateMachine()
    m.on_call_connected(0.0)
    m.on_agent_vad_start(1.0)
    m.on_agent_transcript("Hello.", 1.5)
    m.on_agent_vad_stop(1.6)
    m.on_call_ended(2.0)
    store.save_artifacts(call_dir, m, 0.0, meta={"scenario": scenario, "call_sid": "CA1"})
    if with_recording:
        (call_dir / "recording.mp3").write_bytes(b"ID3fake")
    if findings is not None:
        (call_dir / "findings.json").write_text(json.dumps(findings))
    return call_dir


class TestDashboard:
    def test_index_serves_ui(self, tmp_path):
        client = TestClient(create_dashboard_app(tmp_path))
        resp = client.get("/")
        assert resp.status_code == 200
        assert "mission control" in resp.text

    def test_api_lists_calls_with_findings(self, tmp_path):
        seed_call(tmp_path, "refill", findings=[{"title": "t", "severity": "low"}])
        seed_call(tmp_path, "cancel")
        client = TestClient(create_dashboard_app(tmp_path))
        calls = client.get("/api/calls").json()
        assert [c["id"] for c in calls] == ["01-refill", "02-cancel"]
        assert calls[0]["findings"][0]["title"] == "t"
        assert calls[1]["findings"] is None

    def test_recording_served_and_guarded(self, tmp_path):
        seed_call(tmp_path, "refill", with_recording=True)
        client = TestClient(create_dashboard_app(tmp_path))
        ok = client.get("/api/calls/01-refill/recording.mp3")
        assert ok.status_code == 200
        assert ok.headers["content-type"] == "audio/mpeg"

        missing = client.get("/api/calls/02-none/recording.mp3")
        assert missing.status_code == 404

        traversal = client.get("/api/calls/%2E%2E/recording.mp3")
        assert traversal.status_code in (404, 400)
