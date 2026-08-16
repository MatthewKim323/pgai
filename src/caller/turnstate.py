"""Turn-state machine for the patient caller.

Pure and synchronous: no asyncio, no Pipecat, no I/O. The pipeline feeds
signals in (VAD edges, transcript finals, LLM/TTS lifecycle) and gets back a
list of events describing what changed. Keeping this pure means the entire
turn-taking policy -- including barge-in handling -- is unit-testable without
a phone call.

Roles are inverted from a typical voice agent: *we* are the caller and the
remote party is the AI receptionist under test. So "inbound" audio is the
agent talking, and "outbound" speech is our simulated patient.

States:
    dialing           call placed, media stream not yet connected
    waiting_greeting  connected; the agent answers the phone and speaks first
    agent_speaking    inbound VAD is active (the agent is talking)
    thinking          agent finished a turn; patient LLM is generating
    patient_speaking  our TTS audio is playing
    overlap           the agent started talking over our speech
    ended             call torn down

Barge-in policy (what to do when the agent talks over us):
    yield  stop speaking and listen -- what a polite human does. Default.
    hold   keep talking -- used by scenarios that stress the agent's own
           barge-in handling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "BargeInPolicy",
    "CallState",
    "StateEvent",
    "TurnStateMachine",
]


class CallState(StrEnum):
    DIALING = "dialing"
    WAITING_GREETING = "waiting_greeting"
    AGENT_SPEAKING = "agent_speaking"
    THINKING = "thinking"
    PATIENT_SPEAKING = "patient_speaking"
    OVERLAP = "overlap"
    ENDED = "ended"


class BargeInPolicy(StrEnum):
    YIELD = "yield"
    HOLD = "hold"


# Event types (constants so the pipeline, timeline log, and dashboard agree).
EV_STATE = "state_changed"
EV_AGENT_SAID = "agent_said"
EV_PATIENT_SAID = "patient_said"
EV_AGENT_BARGE_IN = "agent_barge_in"
EV_CANCEL_SPEECH = "cancel_patient_speech"
EV_TURN_COMPLETE = "turn_complete"


@dataclass
class StateEvent:
    """One observable thing that happened, stamped with the caller's clock."""

    type: str
    state: CallState
    ts: float
    turn: int
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Turn:
    """Timing marks for one agent-then-patient exchange."""

    index: int
    agent_stop_ts: float | None = None
    llm_first_token_ts: float | None = None
    tts_first_audio_ts: float | None = None
    patient_stop_ts: float | None = None
    interrupted: bool = False


class TurnStateMachine:
    """Feed signals in; get `StateEvent`s out. All timestamps are supplied by
    the caller (the pipeline clock), never read from a wall clock here."""

    def __init__(self, barge_in_policy: BargeInPolicy = BargeInPolicy.YIELD) -> None:
        self.state = CallState.DIALING
        self.policy = barge_in_policy
        self.turn_index = 0
        self.turns: list[Turn] = [Turn(index=0)]
        self.events: list[StateEvent] = []

    # -- internals ---------------------------------------------------------

    @property
    def _turn(self) -> Turn:
        return self.turns[-1]

    def _emit(self, type_: str, ts: float, **data: Any) -> StateEvent:
        ev = StateEvent(type=type_, state=self.state, ts=ts, turn=self.turn_index, data=data)
        self.events.append(ev)
        return ev

    def _transition(self, new: CallState, ts: float) -> list[StateEvent]:
        if new is self.state:
            return []
        old, self.state = self.state, new
        return [self._emit(EV_STATE, ts, frm=old.value, to=new.value)]

    def _next_turn(self, ts: float) -> None:
        self._emit(EV_TURN_COMPLETE, ts)
        self.turn_index += 1
        self.turns.append(Turn(index=self.turn_index))

    # -- signals from the pipeline ----------------------------------------

    def on_call_connected(self, ts: float) -> list[StateEvent]:
        return self._transition(CallState.WAITING_GREETING, ts)

    def on_agent_vad_start(self, ts: float) -> list[StateEvent]:
        if self.state is CallState.ENDED:
            return []
        if self.state is CallState.PATIENT_SPEAKING:
            # The agent is talking over us.
            self._turn.interrupted = True
            out = self._transition(CallState.OVERLAP, ts)
            out.append(self._emit(EV_AGENT_BARGE_IN, ts, policy=self.policy.value))
            if self.policy is BargeInPolicy.YIELD:
                out.append(self._emit(EV_CANCEL_SPEECH, ts))
            return out
        if self.state in (CallState.WAITING_GREETING, CallState.THINKING):
            return self._transition(CallState.AGENT_SPEAKING, ts)
        # AGENT_SPEAKING / OVERLAP: duplicate edge, nothing to do.
        return []

    def on_agent_vad_stop(self, ts: float) -> list[StateEvent]:
        if self.state is CallState.AGENT_SPEAKING:
            self._turn.agent_stop_ts = ts
            return self._transition(CallState.THINKING, ts)
        if self.state is CallState.OVERLAP:
            # Agent stopped talking over us.
            if self.policy is BargeInPolicy.HOLD:
                # We never stopped; back to plain patient speech.
                return self._transition(CallState.PATIENT_SPEAKING, ts)
            # We yielded, so the agent's interjection was a full turn.
            self._turn.agent_stop_ts = ts
            return self._transition(CallState.THINKING, ts)
        return []

    def on_agent_transcript(self, text: str, ts: float) -> list[StateEvent]:
        """A final STT segment for the agent's speech."""
        if self.state is CallState.ENDED or not text.strip():
            return []
        return [self._emit(EV_AGENT_SAID, ts, text=text.strip())]

    def on_llm_first_token(self, ts: float) -> list[StateEvent]:
        if self._turn.llm_first_token_ts is None:
            self._turn.llm_first_token_ts = ts
        return []

    def on_patient_utterance(self, text: str, ts: float) -> list[StateEvent]:
        """The patient LLM committed a sentence (what our TTS will speak)."""
        if self.state is CallState.ENDED or not text.strip():
            return []
        return [self._emit(EV_PATIENT_SAID, ts, text=text.strip())]

    def on_tts_started(self, ts: float) -> list[StateEvent]:
        if self.state is CallState.ENDED:
            return []
        if self._turn.tts_first_audio_ts is None:
            self._turn.tts_first_audio_ts = ts
        return self._transition(CallState.PATIENT_SPEAKING, ts)

    def on_tts_stopped(self, ts: float) -> list[StateEvent]:
        if self.state is CallState.PATIENT_SPEAKING:
            self._turn.patient_stop_ts = ts
            self._next_turn(ts)
            return self._transition(CallState.WAITING_GREETING, ts)
        if self.state is CallState.OVERLAP:
            # Our audio drained (yield-cancel finishing, or hold running dry)
            # while the agent is still talking.
            self._turn.patient_stop_ts = ts
            self._next_turn(ts)
            return self._transition(CallState.AGENT_SPEAKING, ts)
        return []

    def on_call_ended(self, ts: float, reason: str = "hangup") -> list[StateEvent]:
        if self.state is CallState.ENDED:
            return []
        out = self._transition(CallState.ENDED, ts)
        out.append(self._emit("call_ended", ts, reason=reason))
        return out

    # -- serialization -----------------------------------------------------

    def timeline(self) -> list[dict[str, Any]]:
        return [
            {"type": e.type, "state": e.state.value, "ts": e.ts, "turn": e.turn, **e.data}
            for e in self.events
        ]
