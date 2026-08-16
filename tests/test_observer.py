"""Observer: pipecat frames -> turn-state signals, with per-frame dedupe."""

import pytest
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    EndFrame,
    LLMFullResponseEndFrame,
    LLMTextFrame,
    StartFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import FramePushed

from caller.observer import TurnStateObserver
from caller.turnstate import CallState, TurnStateMachine

NS = 1_000_000_000


async def push(obs: TurnStateObserver, frame, secs: float):
    await obs.on_push_frame(
        FramePushed(
            source=None, destination=None, frame=frame, direction=None,
            timestamp=int(secs * NS),
        )
    )


@pytest.fixture
def obs() -> TurnStateObserver:
    return TurnStateObserver(TurnStateMachine())


class TestObserver:
    async def test_full_exchange(self, obs):
        m = obs.machine
        await push(obs, StartFrame(), 0.0)
        assert m.state is CallState.WAITING_GREETING
        assert obs.call_start_ts == 0.0

        await push(obs, UserStartedSpeakingFrame(), 1.0)
        assert m.state is CallState.AGENT_SPEAKING
        await push(obs, TranscriptionFrame(text="How can I help?", user_id="", timestamp=""), 2.5)
        await push(obs, UserStoppedSpeakingFrame(), 3.0)
        assert m.state is CallState.THINKING

        await push(obs, LLMTextFrame(text="Hi, I need "), 3.5)
        await push(obs, LLMTextFrame(text="a refill."), 3.6)
        await push(obs, LLMFullResponseEndFrame(), 3.7)
        await push(obs, BotStartedSpeakingFrame(), 3.9)
        assert m.state is CallState.PATIENT_SPEAKING
        await push(obs, BotStoppedSpeakingFrame(), 6.0)
        assert m.state is CallState.WAITING_GREETING

        # llm text accumulated into one utterance; first-token latency marked
        said = [e for e in m.events if e.type == "patient_said"]
        assert said[0].data["text"] == "Hi, I need a refill."
        assert m.turns[0].llm_first_token_ts == 3.5
        assert m.turns[0].agent_stop_ts == 3.0

    async def test_frames_deduped_across_hops(self, obs):
        frame = UserStartedSpeakingFrame()
        await push(obs, StartFrame(), 0.0)
        await push(obs, frame, 1.0)
        await push(obs, frame, 1.01)  # same frame instance seen at the next hop
        vad_events = [e for e in obs.machine.events if e.type == "state_changed"]
        assert len([e for e in vad_events if e.data.get("to") == "agent_speaking"]) == 1

    async def test_end_frame_ends_call(self, obs):
        await push(obs, StartFrame(), 0.0)
        await push(obs, EndFrame(), 5.0)
        assert obs.machine.state is CallState.ENDED
