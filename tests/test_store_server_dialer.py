"""Artifact store, TwiML generation, and the dialer's guard rails."""

from unittest.mock import MagicMock

import pytest

from caller import store
from caller.config import ConfigError, load_config
from caller.dialer import place_call
from caller.server import twiml_for_scenario
from caller.turnstate import TurnStateMachine
from tests.test_config import GOOD_ENV


def driven_machine() -> TurnStateMachine:
    m = TurnStateMachine()
    m.on_call_connected(0.0)
    m.on_agent_vad_start(1.0)
    m.on_agent_transcript("Hello, Pivot Point.", 2.0)
    m.on_agent_vad_stop(2.2)
    m.on_llm_first_token(2.6)
    m.on_patient_utterance("Hi there.", 2.7)
    m.on_tts_started(2.9)
    m.on_tts_stopped(4.0)
    m.on_call_ended(5.0)
    return m


class TestStore:
    def test_sequential_numbering(self, tmp_path):
        a = store.create_call_dir("refill", tmp_path)
        b = store.create_call_dir("cancel", tmp_path)
        assert a.name == "01-refill"
        assert b.name == "02-cancel"

    def test_numbering_survives_gaps(self, tmp_path):
        (tmp_path / "07-old").mkdir(parents=True)
        c = store.create_call_dir("refill", tmp_path)
        assert c.name == "08-refill"

    def test_save_and_load_roundtrip(self, tmp_path):
        call_dir = store.create_call_dir("refill", tmp_path)
        store.save_artifacts(call_dir, driven_machine(), 0.0, meta={"scenario": "refill"})

        loaded = store.load_call(call_dir)
        assert loaded["meta"]["scenario"] == "refill"
        assert "AGENT: Hello, Pivot Point." in loaded["transcript_text"]
        assert loaded["telemetry"]["completed_turns"] == 1
        assert loaded["timeline"][0]["type"] == "state_changed"
        assert loaded["recording"] is None  # no mp3 yet

    def test_list_calls_orders_and_filters(self, tmp_path):
        store.create_call_dir("b", tmp_path)
        store.create_call_dir("a", tmp_path)
        (tmp_path / "not-a-call").mkdir()
        names = [p.name for p in store.list_calls(tmp_path)]
        assert names == ["01-b", "02-a"]


class TestTwiml:
    def test_websocket_url_and_scenario_param(self):
        cfg = load_config(GOOD_ENV)
        xml = twiml_for_scenario(cfg, "edge-rambler")
        assert 'url="wss://abc.ngrok.app/ws"' in xml
        assert '<Parameter name="scenario" value="edge-rambler"' in xml


class TestDialer:
    def test_refuses_non_test_targets(self, monkeypatch):
        monkeypatch.delenv("I_KNOW_WHAT_IM_DOING", raising=False)
        cfg = load_config({**GOOD_ENV, "TARGET_NUMBER": "+13105551234"})
        with pytest.raises(ConfigError, match="refusing to dial"):
            place_call(cfg, "refill", client=MagicMock())

    def test_places_recorded_dual_channel_call(self):
        cfg = load_config(GOOD_ENV)
        client = MagicMock()
        client.calls.create.return_value.sid = "CA123"
        sid = place_call(cfg, "refill", client=client)
        assert sid == "CA123"
        kwargs = client.calls.create.call_args.kwargs
        assert kwargs["to"] == cfg.target_number
        assert kwargs["record"] is True
        assert kwargs["recording_channels"] == "dual"
        assert kwargs["url"].endswith("/twiml?scenario=refill")
