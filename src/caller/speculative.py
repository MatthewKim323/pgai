"""Speculative generation: start the reply before the turn officially ends.

The cascaded pipeline's response latency is turn-detection + LLM
time-to-first-token + TTS, in series. But the STT's *final* segment for the
agent's sentence usually lands well before the turn-stop machinery (VAD
silence + smart-turn) declares the turn over. That window is free real
estate: we build the exact request the LLM service is about to make, open
the stream early, and let tokens buffer while the pipeline is still deciding
the agent has finished talking.

When the real request arrives, its messages are compared to the speculated
ones on normalized text (STT can commit one segment as a string and another
as a list of text blocks; same words, different shape). Match: the
pre-started stream is handed over and first tokens are already in hand.
Miss: the speculation is closed and the normal request proceeds -- the only
cost is a few wasted tokens.

The same idea ships in production stacks as livekit-agents'
`preemptive_generation`; this is the pipecat-shaped version, on the
`_create_message_stream` seam so the service's own retry/timeout and frame
plumbing stay untouched.
"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger
from pipecat.frames.frames import Frame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.anthropic.llm import AnthropicLLMService


def normalize_messages(messages: list[dict[str, Any]]) -> str:
    """Shape-insensitive fingerprint of a message list.

    Text content is flattened and whitespace-normalized; non-text blocks
    (tool_use / tool_result) contribute type markers so a turn with tool
    traffic can never falsely match a plain-text speculation.
    """
    out = []
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            text = content
        else:
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif isinstance(block, dict):
                    parts.append(f"<{block.get('type')}>")
            text = " ".join(parts)
        out.append(f"{m.get('role')}:{' '.join(text.split()).lower()}")
    return "\n".join(out)


class Speculator:
    """Holds at most one in-flight speculation."""

    def __init__(self) -> None:
        self._key: str | None = None
        self._task: asyncio.Task | None = None
        self.hits = 0
        self.misses = 0

    def start(self, key: str, coro) -> None:
        """Begin a new speculation, superseding any previous one."""
        if key == self._key:
            return  # already speculating on exactly this content
        self.cancel()
        self._key = key
        self._task = asyncio.create_task(coro)

    async def take(self, key: str):
        """Claim the speculated stream if it matches; None on any mismatch."""
        task, our_key = self._task, self._key
        self._key, self._task = None, None
        if task is None:
            return None
        if key != our_key:
            self.misses += 1
            _discard(task)
            return None
        try:
            stream = await task
            self.hits += 1
            logger.debug(f"speculation HIT ({self.hits} hits / {self.misses} misses)")
            return stream
        except Exception as e:  # noqa: BLE001 - speculation must never break the real path
            logger.warning(f"speculation failed, falling back: {e}")
            return None

    def cancel(self) -> None:
        if self._task is not None:
            _discard(self._task)
        self._key, self._task = None, None


def _discard(task: asyncio.Task) -> None:
    """Cancel or drain an unclaimed speculation without awaiting it here."""

    async def _close() -> None:
        try:
            if not task.done():
                task.cancel()
                return
            stream = task.exception() is None and task.result()
            if stream and hasattr(stream, "close"):
                await stream.close()
        except Exception:  # noqa: BLE001 - best-effort cleanup
            pass

    asyncio.get_event_loop().create_task(_close())


class SpeculativeAnthropicLLMService(AnthropicLLMService):
    """AnthropicLLMService that can be handed a pre-started stream."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.speculator = Speculator()

    def build_request_params(self, context) -> dict[str, Any]:
        """The exact params `_process_context` would build for this context."""
        params: dict[str, Any] = {
            "model": self._settings.model,
            "max_tokens": self._settings.max_tokens,
            "stream": True,
            "temperature": self._settings.temperature,
            "top_k": self._settings.top_k,
            "top_p": self._settings.top_p,
        }
        params.update(self._get_llm_invocation_params(context))
        params.update(self._settings.extra)
        params.update({"betas": ["interleaved-thinking-2025-05-14"]})
        return params

    def speculate_on(self, context, pending_user_text: str) -> None:
        """Open a stream for `context` + the not-yet-committed user text."""
        from pipecat.processors.aggregators.llm_context import LLMContext

        clone = LLMContext(
            messages=[*context.get_messages(), {"role": "user", "content": pending_user_text}],
            tools=context.tools,
        )
        params = self.build_request_params(clone)
        key = normalize_messages(params["messages"])
        self.speculator.start(key, self._client.beta.messages.create(**params))

    async def _create_message_stream(self, api_call, params):
        speculated = await self.speculator.take(normalize_messages(params["messages"]))
        if speculated is not None:
            return speculated
        return await super()._create_message_stream(api_call, params)


class SpeculationTap(FrameProcessor):
    """Sits between STT and the user aggregator; fires a speculation on every
    final STT segment (the committed turn is the concatenation of segments,
    so each new segment re-speculates with the fuller text)."""

    def __init__(self, llm: SpeculativeAnthropicLLMService, context) -> None:
        super().__init__()
        self._llm = llm
        self._context = context
        self._segments: list[str] = []
        self._context_len = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame) and frame.text.strip():
            # A grown context means the aggregator committed the previous turn
            # (commit frames flow downstream of us, so we can't observe them
            # directly); stale segments belong to history now.
            current_len = len(self._context.get_messages())
            if current_len != self._context_len:
                self._context_len = current_len
                self._segments = []
            self._segments.append(frame.text.strip())
            try:
                self._llm.speculate_on(self._context, " ".join(self._segments))
            except Exception as e:  # noqa: BLE001 - never let speculation break the pipeline
                logger.warning(f"speculation start failed: {e}")
        await self.push_frame(frame, direction)
