"""CLI plumbing + call-dir correlation (no network, no telephony)."""

import json

from caller import store
from caller.__main__ import main
from caller.orchestrate import find_call_dir
from caller.turnstate import TurnStateMachine


def make_call_dir(tmp_path, scenario: str, call_sid: str):
    call_dir = store.create_call_dir(scenario, tmp_path)
    m = TurnStateMachine()
    m.on_call_connected(0.0)
    m.on_call_ended(1.0)
    store.save_artifacts(call_dir, m, 0.0, meta={"scenario": scenario, "call_sid": call_sid})
    return call_dir


class TestFindCallDir:
    def test_correlates_on_call_sid(self, tmp_path):
        make_call_dir(tmp_path, "refill", "CA111")
        want = make_call_dir(tmp_path, "cancel", "CA222")
        assert find_call_dir("CA222", tmp_path, timeout_secs=2) == want

    def test_prefers_newest_match_first(self, tmp_path):
        # newest dirs are checked first, so a fresh call wins immediately
        make_call_dir(tmp_path, "refill", "CA111")
        newest = make_call_dir(tmp_path, "refill", "CA333")
        assert find_call_dir("CA333", tmp_path, timeout_secs=2) == newest

    def test_times_out_to_none(self, tmp_path):
        make_call_dir(tmp_path, "refill", "CA111")
        assert find_call_dir("CA999", tmp_path, timeout_secs=0.5) is None

    def test_tolerates_incomplete_dirs(self, tmp_path):
        (tmp_path / "01-broken").mkdir(parents=True)  # no meta.json
        want = make_call_dir(tmp_path, "refill", "CA444")
        assert find_call_dir("CA444", tmp_path, timeout_secs=2) == want


class TestCli:
    def test_list_runs_without_config(self, capsys):
        assert main(["list"]) == 0
        out = capsys.readouterr().out
        assert "refill" in out
        assert "edge-weekend-booking" in out

    def test_call_with_missing_env_fails_cleanly(self, monkeypatch, capsys):
        for key in (
            "TWILIO_ACCOUNT_SID",
            "TWILIO_AUTH_TOKEN",
            "TWILIO_FROM_NUMBER",
            "PUBLIC_BASE_URL",
            "DEEPGRAM_API_KEY",
            "ANTHROPIC_API_KEY",
            "ELEVENLABS_API_KEY",
        ):
            monkeypatch.delenv(key, raising=False)
        assert main(["call", "refill"]) == 2
        assert "missing required environment" in capsys.readouterr().err

    def test_unknown_scenario_fails_cleanly(self, monkeypatch, capsys):
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC1")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "t")
        monkeypatch.setenv("TWILIO_FROM_NUMBER", "+16265551234")
        monkeypatch.setenv("PUBLIC_BASE_URL", "https://x.ngrok.app")
        monkeypatch.setenv("DEEPGRAM_API_KEY", "d")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
        monkeypatch.setenv("ELEVENLABS_API_KEY", "e")
        assert main(["call", "no-such-scenario"]) == 2
        assert "not found" in capsys.readouterr().err

    def test_campaign_requires_scenarios(self, capsys):
        assert main(["campaign"]) == 2


def test_meta_json_shape(tmp_path):
    call_dir = make_call_dir(tmp_path, "refill", "CA555")
    meta = json.loads((call_dir / "meta.json").read_text())
    assert meta["call_sid"] == "CA555"
    assert "saved_at" in meta
