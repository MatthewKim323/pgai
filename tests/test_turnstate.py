"""Turn-state machine: full turn cycle, barge-in policies, edge tolerance."""

from caller.turnstate import (
    EV_AGENT_BARGE_IN,
    EV_AGENT_SAID,
    EV_CANCEL_SPEECH,
    EV_PATIENT_SAID,
    EV_STATE,
    EV_TURN_COMPLETE,
    BargeInPolicy,
    CallState,
    TurnStateMachine,
)


def drive_one_turn(m: TurnStateMachine, t0: float = 0.0) -> None:
    """Connected call -> agent greets -> patient replies -> back to waiting."""
    m.on_call_connected(t0)
    m.on_agent_vad_start(t0 + 1.0)
    m.on_agent_transcript("Thank you for calling Pivot Point Orthopedics.", t0 + 3.0)
    m.on_agent_vad_stop(t0 + 3.2)
    m.on_llm_first_token(t0 + 3.6)
    m.on_patient_utterance("Hi, I'd like to book an appointment.", t0 + 3.7)
    m.on_tts_started(t0 + 3.9)
    m.on_tts_stopped(t0 + 6.0)


class TestHappyTurn:
    def test_state_walk(self):
        m = TurnStateMachine()
        assert m.state is CallState.DIALING
        m.on_call_connected(0.0)
        assert m.state is CallState.WAITING_GREETING
        m.on_agent_vad_start(1.0)
        assert m.state is CallState.AGENT_SPEAKING
        m.on_agent_vad_stop(3.2)
        assert m.state is CallState.THINKING
        m.on_tts_started(3.9)
        assert m.state is CallState.PATIENT_SPEAKING
        m.on_tts_stopped(6.0)
        assert m.state is CallState.WAITING_GREETING

    def test_turn_marks_recorded(self):
        m = TurnStateMachine()
        drive_one_turn(m)
        t = m.turns[0]
        assert t.agent_stop_ts == 3.2
        assert t.llm_first_token_ts == 3.6
        assert t.tts_first_audio_ts == 3.9
        assert t.patient_stop_ts == 6.0
        assert not t.interrupted

    def test_turn_advances_after_patient_finishes(self):
        m = TurnStateMachine()
        drive_one_turn(m)
        assert m.turn_index == 1
        assert [e for e in m.events if e.type == EV_TURN_COMPLETE]

    def test_transcript_events_carry_text(self):
        m = TurnStateMachine()
        drive_one_turn(m)
        agent = [e for e in m.events if e.type == EV_AGENT_SAID]
        patient = [e for e in m.events if e.type == EV_PATIENT_SAID]
        assert agent[0].data["text"].startswith("Thank you for calling")
        assert patient[0].data["text"].startswith("Hi, I'd like")


class TestBargeIn:
    def _to_patient_speaking(self) -> TurnStateMachine:
        m = TurnStateMachine()
        m.on_call_connected(0.0)
        m.on_agent_vad_start(1.0)
        m.on_agent_vad_stop(3.0)
        m.on_tts_started(3.5)
        assert m.state is CallState.PATIENT_SPEAKING
        return m

    def test_yield_policy_cancels_speech(self):
        m = self._to_patient_speaking()
        events = m.on_agent_vad_start(4.0)
        assert m.state is CallState.OVERLAP
        types = [e.type for e in events]
        assert EV_AGENT_BARGE_IN in types
        assert EV_CANCEL_SPEECH in types
        assert m.turns[-1].interrupted

    def test_yield_treats_interjection_as_agent_turn(self):
        m = self._to_patient_speaking()
        m.on_agent_vad_start(4.0)
        m.on_tts_stopped(4.1)  # our audio drains after the cancel
        assert m.state is CallState.AGENT_SPEAKING
        m.on_agent_vad_stop(6.0)
        assert m.state is CallState.THINKING

    def test_hold_policy_keeps_talking(self):
        m = TurnStateMachine(barge_in_policy=BargeInPolicy.HOLD)
        m.on_call_connected(0.0)
        m.on_agent_vad_start(1.0)
        m.on_agent_vad_stop(3.0)
        m.on_tts_started(3.5)
        events = m.on_agent_vad_start(4.0)
        assert m.state is CallState.OVERLAP
        assert EV_CANCEL_SPEECH not in [e.type for e in events]
        # agent gives up; we are still mid-speech
        m.on_agent_vad_stop(5.0)
        assert m.state is CallState.PATIENT_SPEAKING

    def test_overlap_transcript_still_recorded(self):
        m = self._to_patient_speaking()
        m.on_agent_vad_start(4.0)
        events = m.on_agent_transcript("Sorry to interrupt", 4.5)
        assert events[0].data["text"] == "Sorry to interrupt"


class TestEdgeTolerance:
    def test_duplicate_vad_edges_are_noops(self):
        m = TurnStateMachine()
        m.on_call_connected(0.0)
        m.on_agent_vad_start(1.0)
        assert m.on_agent_vad_start(1.1) == []
        m.on_agent_vad_stop(2.0)
        assert m.on_agent_vad_stop(2.1) == []

    def test_empty_transcripts_dropped(self):
        m = TurnStateMachine()
        m.on_call_connected(0.0)
        assert m.on_agent_transcript("   ", 1.0) == []

    def test_signals_after_end_are_ignored(self):
        m = TurnStateMachine()
        drive_one_turn(m)
        m.on_call_ended(7.0)
        assert m.on_agent_vad_start(8.0) == []
        assert m.on_agent_transcript("hello?", 8.1) == []
        assert m.on_tts_started(8.2) == []
        assert m.state is CallState.ENDED

    def test_end_is_idempotent(self):
        m = TurnStateMachine()
        m.on_call_connected(0.0)
        assert m.on_call_ended(1.0, reason="agent_hangup")
        assert m.on_call_ended(1.1) == []


class TestTimeline:
    def test_timeline_is_flat_json_friendly(self):
        m = TurnStateMachine()
        drive_one_turn(m)
        m.on_call_ended(7.0)
        tl = m.timeline()
        assert all({"type", "state", "ts", "turn"} <= set(row) for row in tl)
        state_rows = [r for r in tl if r["type"] == EV_STATE]
        assert state_rows[0]["frm"] == "dialing"
        assert state_rows[-1]["to"] == "ended"
