"""Transcript projection + telemetry, driven through the real state machine."""

from caller import telemetry, transcript
from caller.turnstate import TurnStateMachine


def scripted_call() -> TurnStateMachine:
    """Two clean exchanges, then an agent barge-in, then hangup."""
    m = TurnStateMachine()
    m.on_call_connected(10.0)  # nonzero start: transcript must rebase to 0

    # turn 0: greeting -> patient asks
    m.on_agent_vad_start(11.0)
    m.on_agent_transcript("Thank you for calling Pivot Point Orthopedics.", 13.0)
    m.on_agent_transcript("How can I help you today?", 13.8)  # merges: gap < 2s
    m.on_agent_vad_stop(14.0)
    m.on_llm_first_token(14.5)
    m.on_patient_utterance("Hi, I need to refill my meloxicam.", 14.6)
    m.on_tts_started(14.8)
    m.on_tts_stopped(17.0)

    # turn 1: agent responds slowly (3s gap -> agent-side finding)
    m.on_agent_vad_start(20.0)
    m.on_agent_transcript("Sure, can I get your date of birth?", 21.5)
    m.on_agent_vad_stop(21.7)
    m.on_llm_first_token(22.1)
    m.on_patient_utterance("It's March 23rd, 2006.", 22.2)
    m.on_tts_started(22.4)

    # agent barges in while we speak; our audio drains, agent keeps talking
    m.on_agent_vad_start(23.0)
    m.on_tts_stopped(23.2)
    m.on_agent_transcript("Sorry, one moment.", 23.5)

    m.on_call_ended(26.0)
    return m


class TestTranscript:
    def test_projection_and_merge(self):
        m = scripted_call()
        entries = transcript.from_events(m.events, call_start_ts=10.0)
        # the two greeting finals merged into one agent line
        assert entries[0].speaker == "agent"
        assert "How can I help you today?" in entries[0].text
        assert entries[0].ts == 3.0
        speakers = [e.speaker for e in entries]
        assert speakers == ["agent", "patient", "agent", "patient", "agent"]

    def test_no_merge_across_speakers_or_big_gaps(self):
        m = scripted_call()
        entries = transcript.from_events(m.events, call_start_ts=10.0)
        agent_lines = [e for e in entries if e.speaker == "agent"]
        # the 20s agent line must NOT merge into the 13s greeting
        assert len(agent_lines) == 3

    def test_text_render_format(self):
        m = scripted_call()
        text = transcript.to_text(transcript.from_events(m.events, call_start_ts=10.0))
        lines = text.splitlines()
        assert lines[0].startswith("[00:03] AGENT: Thank you for calling")
        assert any(line.startswith("[00:04] PATIENT:") for line in lines)

    def test_json_render(self):
        m = scripted_call()
        rows = transcript.to_json(transcript.from_events(m.events, call_start_ts=10.0))
        assert rows[0]["stamp"] == "00:03"
        assert {"speaker", "text", "ts", "stamp"} <= set(rows[0])


class TestTelemetry:
    def test_patient_turn_metrics(self):
        m = scripted_call()
        rows = telemetry.patient_turn_metrics(m.turns)
        t0 = rows[0]
        assert t0["llm_first_token"] == 0.5
        assert t0["response_latency"] == 0.8  # 14.8 - 14.0
        assert t0["speech_duration"] == 2.2
        assert not t0["interrupted"]
        assert rows[1]["interrupted"]

    def test_agent_response_gaps(self):
        m = scripted_call()
        gaps = telemetry.agent_response_gaps(m.events)
        # 1.0s to greet after connect; 3.0s to respond after our first turn
        assert gaps == [1.0, 3.0]

    def test_report_shape(self):
        m = scripted_call()
        report = telemetry.build_report(m.turns, m.events)
        assert report["completed_turns"] == 2
        assert report["interruptions"] == 1
        assert report["patient"]["response_latency"]["p50"] == 0.75
        assert report["agent_under_test"]["response_gap"]["max"] == 3.0
        assert report["call_duration_secs"] == 16.0

    def test_empty_call_degrades(self):
        m = TurnStateMachine()
        m.on_call_connected(0.0)
        m.on_call_ended(1.0)
        report = telemetry.build_report(m.turns, m.events)
        assert report["completed_turns"] == 0
        assert report["patient"]["response_latency"] is None
