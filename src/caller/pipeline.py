"""Voice pipeline assembly: one phone call = one pipeline run.

Latency posture (the whole game for a voice bot):
- Cloud trio tuned for time-to-first-byte: Deepgram nova-3 streaming STT,
  Claude Haiku for fast first tokens, ElevenLabs turbo TTS.
- Turn endpointing uses pipecat's local smart-turn model (semantic end-of-turn
  on top of Silero VAD) instead of a fat fixed silence gap.
- Interruption handling is framework-level cancel-and-flush; scenarios with
  `barge_in_policy: hold` disable it to stress the agent's own barge-in.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from fastapi import WebSocket
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import EndFrame, LLMMessagesAppendFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.anthropic.llm import AnthropicLLMService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.turns.user_start import (
    TranscriptionUserTurnStartStrategy,
    VADUserTurnStartStrategy,
)
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.workers.runner import WorkerRunner

from caller.config import Config
from caller.observer import TurnStateObserver
from caller.scenario import Scenario, build_system_prompt
from caller.turnstate import BargeInPolicy, TurnStateMachine

#: time between the "wrap up now" nudge and the hard EndFrame, so a wedged
#: call can't run a phone bill forever
WRAP_UP_GRACE_SECS = 45.0

END_CALL_TOOL = FunctionSchema(
    name="end_call",
    description=(
        "Hang up the phone. Call this only AFTER you have said your goodbye "
        "out loud. The call ends a moment later, once your goodbye finishes playing."
    ),
    properties={},
    required=[],
)


def build_tts(cfg: Config, scenario: Scenario):
    """The patient's voice. Deepgram Aura-2 by default (same vendor as STT,
    already funded, built for agent latency); ElevenLabs turbo as the opt-in
    upgrade. The scenario's voice_id is provider-specific and wins when set."""
    voice = scenario.persona.voice_id or cfg.default_voice
    if cfg.tts_provider == "elevenlabs":
        return ElevenLabsTTSService(
            api_key=cfg.elevenlabs_api_key, voice_id=voice, model="eleven_turbo_v2_5"
        )
    return DeepgramTTSService(
        api_key=cfg.deepgram_api_key, settings=DeepgramTTSService.Settings(voice=voice)
    )


@dataclass
class CallResult:
    machine: TurnStateMachine
    observer: TurnStateObserver
    messages: list[dict]
    ended_by: str


async def run_call_pipeline(
    websocket: WebSocket,
    stream_sid: str,
    call_sid: str,
    scenario: Scenario,
    cfg: Config,
) -> CallResult:
    """Drive one call to completion; returns the full turn-state record."""
    machine = TurnStateMachine(barge_in_policy=scenario.barge_in_policy)
    observer = TurnStateObserver(machine)
    ended_by = "remote_hangup"

    serializer = TwilioFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        account_sid=cfg.twilio_account_sid,
        auth_token=cfg.twilio_auth_token,  # enables auto hang-up on EndFrame
    )
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )

    # defaults to nova-3-general with streaming interim results
    stt = DeepgramSTTService(api_key=cfg.deepgram_api_key)
    # Prompt caching shaves time-to-first-token on every turn after the first
    # (the persona system prompt dominates the context); max_tokens capped
    # because phone replies are short and runaway generations block the turn.
    llm = AnthropicLLMService(
        api_key=cfg.anthropic_api_key,
        settings=AnthropicLLMService.Settings(
            model=cfg.patient_model, enable_prompt_caching=True, max_tokens=300
        ),
    )
    tts = build_tts(cfg, scenario)

    context = LLMContext(
        messages=[{"role": "system", "content": build_system_prompt(scenario)}],
        tools=ToolsSchema(standard_tools=[END_CALL_TOOL]),
    )

    # Barge-in policy: 'yield' lets the framework cancel our speech when the
    # agent talks over us (polite caller). 'hold' turns interruption off so we
    # keep talking -- the point of those scenarios is to stress the AGENT's
    # barge-in handling, and the observer records the overlap either way.
    #
    # stop_secs stays at pipecat's recommended 0.2: raising it past the STT's
    # p99 collapses the transcript wait and stalls turns on the 5s aggregator
    # timeout instead (measured on shakedown call 01: 4-6s response latency).
    vad = SileroVADAnalyzer(params=VADParams(stop_secs=0.2))
    # When the smart-turn model is unsure the speaker is done, it falls back
    # to a silence timeout; the 3s default read as dead air on the wire
    # (measured 4.9s worst-case turns on calls 01/03). 1.6s of silence is
    # decisive enough on a phone call.
    stop = [
        TurnAnalyzerUserTurnStopStrategy(
            turn_analyzer=LocalSmartTurnAnalyzerV3(params=SmartTurnParams(stop_secs=1.6))
        )
    ]
    if scenario.barge_in_policy is BargeInPolicy.HOLD:
        strategies = UserTurnStrategies(
            start=[
                VADUserTurnStartStrategy(enable_interruptions=False),
                TranscriptionUserTurnStartStrategy(enable_interruptions=False),
            ],
            stop=stop,
        )
    else:
        strategies = UserTurnStrategies(stop=stop)
    user_params = LLMUserAggregatorParams(vad_analyzer=vad, user_turn_strategies=strategies)

    aggregators = LLMContextAggregatorPair(context, user_params=user_params)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            aggregators.user(),
            llm,
            tts,
            transport.output(),
            aggregators.assistant(),
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(audio_in_sample_rate=8000, audio_out_sample_rate=8000),
        observers=[observer],
        # a phone call has natural silences; don't let idle detection kill it
        idle_timeout_secs=60,
    )

    # The remote side hanging up on us is a normal outcome (and sometimes the
    # finding itself -- e.g. a transfer to a dead end). Without this, the
    # websocket dies quietly and the pipeline sits on the idle timeout while
    # the call's artifacts never get written.
    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport, _websocket) -> None:
        await worker.queue_frame(EndFrame())

    async def end_call(params: FunctionCallParams) -> None:
        nonlocal ended_by
        ended_by = "patient_goodbye"
        await params.result_callback({"status": "hanging_up"})
        # EndFrame is uninterruptible and flows behind the goodbye audio, so
        # the farewell finishes playing before the serializer hangs up.
        await worker.queue_frame(EndFrame())

    llm.register_function("end_call", end_call)

    async def watchdog() -> None:
        # Soft: at the scenario's time budget, tell the patient to wrap up so
        # the call ends with a natural goodbye (shakedown call 01 ran into the
        # hard kill mid-sentence). Hard: a grace period later, pull the plug.
        nonlocal ended_by
        await asyncio.sleep(scenario.max_minutes * 60)
        await worker.queue_frame(
            LLMMessagesAppendFrame(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Time is up on this call. On your next reply, wrap up "
                            "immediately: briefly thank them, say goodbye, then call "
                            "the end_call tool. Do not ask anything new."
                        ),
                    }
                ],
                run_llm=False,
            )
        )
        await asyncio.sleep(WRAP_UP_GRACE_SECS)
        ended_by = "watchdog_timeout"
        await worker.queue_frame(EndFrame())

    watchdog_task = asyncio.create_task(watchdog())
    try:
        runner = WorkerRunner(handle_sigint=False)
        await runner.add_workers(worker)
        await runner.run()
    finally:
        watchdog_task.cancel()

    return CallResult(
        machine=machine,
        observer=observer,
        messages=context.get_messages(),
        ended_by=ended_by,
    )
