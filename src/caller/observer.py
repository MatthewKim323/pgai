"""Pipecat observer that narrates the call into the turn-state machine.

Pipecat's naming assumes we're the agent and the remote human is the "user".
On this project the roles are flipped: the remote "user" is the AI
receptionist under test, and the "bot" is our simulated patient. This
observer is where that translation happens -- frames go in, turn-state
signals come out, and nothing else in the codebase has to think about
pipecat's perspective.
"""

from __future__ import annotations

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    CancelFrame,
    EndFrame,
    Frame,
    LLMFullResponseEndFrame,
    LLMTextFrame,
    StartFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed

from caller.turnstate import TurnStateMachine

_NS = 1_000_000_000


class TurnStateObserver(BaseObserver):
    """Feeds pipeline frames into a `TurnStateMachine`.

    A frame is pushed once per processor hop, so every frame is deduped by
    its id and handled exactly once, on first sight.
    """

    def __init__(self, machine: TurnStateMachine) -> None:
        super().__init__()
        self.machine = machine
        self.call_start_ts: float | None = None
        self._seen: set[int] = set()
        self._pending_utterance: list[str] = []

    async def on_push_frame(self, data: FramePushed) -> None:
        frame = data.frame
        if frame.id in self._seen:
            return
        self._seen.add(frame.id)
        self._handle(frame, data.timestamp / _NS)

    def _handle(self, frame: Frame, ts: float) -> None:
        m = self.machine
        if isinstance(frame, StartFrame):
            self.call_start_ts = ts
            m.on_call_connected(ts)
        elif isinstance(frame, UserStartedSpeakingFrame):
            m.on_agent_vad_start(ts)
        elif isinstance(frame, UserStoppedSpeakingFrame):
            m.on_agent_vad_stop(ts)
        elif isinstance(frame, TranscriptionFrame):
            m.on_agent_transcript(frame.text, ts)
        elif isinstance(frame, LLMTextFrame):
            if not self._pending_utterance:
                m.on_llm_first_token(ts)
            self._pending_utterance.append(frame.text)
        elif isinstance(frame, LLMFullResponseEndFrame):
            text = "".join(self._pending_utterance).strip()
            self._pending_utterance = []
            if text:
                m.on_patient_utterance(text, ts)
        elif isinstance(frame, BotStartedSpeakingFrame):
            m.on_tts_started(ts)
        elif isinstance(frame, BotStoppedSpeakingFrame):
            m.on_tts_stopped(ts)
        elif isinstance(frame, EndFrame):
            m.on_call_ended(ts, reason="end_frame")
        elif isinstance(frame, CancelFrame):
            m.on_call_ended(ts, reason="cancelled")
