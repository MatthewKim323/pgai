"""Speculative generation: fingerprinting, claim/miss semantics, the seam."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from caller.speculative import (
    SpeculativeAnthropicLLMService,
    Speculator,
    normalize_messages,
)

MSGS_STRING = [
    {"role": "system", "content": "You are Diane."},
    {"role": "user", "content": "How can  I help you today?"},
]
# same words, different shape: content as text-block list, extra whitespace
MSGS_BLOCKS = [
    {"role": "system", "content": "You are Diane."},
    {"role": "user", "content": [{"type": "text", "text": "How can I help"},
                                 {"type": "text", "text": "you today?"}]},
]


class TestNormalize:
    def test_shape_insensitive(self):
        assert normalize_messages(MSGS_STRING) == normalize_messages(MSGS_BLOCKS)

    def test_text_differences_matter(self):
        other = [dict(MSGS_STRING[0]), {"role": "user", "content": "different words"}]
        assert normalize_messages(MSGS_STRING) != normalize_messages(other)

    def test_tool_blocks_never_match_plain_text(self):
        with_tool = [
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x"}]},
        ]
        plain = [{"role": "user", "content": ""}]
        assert normalize_messages(with_tool) != normalize_messages(plain)


class TestSpeculator:
    async def test_hit_returns_stream(self):
        spec = Speculator()

        async def fake_stream():
            return "THE_STREAM"

        spec.start("key1", fake_stream())
        assert await spec.take("key1") == "THE_STREAM"
        assert spec.hits == 1

    async def test_mismatch_returns_none_and_counts_miss(self):
        spec = Speculator()

        async def fake_stream():
            return MagicMock()

        spec.start("key1", fake_stream())
        assert await spec.take("other-key") is None
        assert spec.misses == 1
        await asyncio.sleep(0)  # let the discard task run

    async def test_take_without_speculation(self):
        assert await Speculator().take("k") is None

    async def test_failed_speculation_falls_back(self):
        spec = Speculator()

        async def boom():
            raise RuntimeError("api down")

        spec.start("key1", boom())
        assert await spec.take("key1") is None

    async def test_restart_supersedes(self):
        spec = Speculator()

        async def stream(name):
            return name

        spec.start("key1", stream("a"))
        spec.start("key2", stream("b"))
        assert await spec.take("key2") == "b"
        await asyncio.sleep(0)


def make_service() -> SpeculativeAnthropicLLMService:
    return SpeculativeAnthropicLLMService(
        api_key="test-key",
        settings=SpeculativeAnthropicLLMService.Settings(
            model="claude-haiku-4-5-20251001", max_tokens=300
        ),
    )


class TestServiceSeam:
    async def test_speculation_consumed_at_seam(self):
        svc = make_service()

        async def fake_stream():
            return "PRESTARTED"

        params = {"messages": MSGS_STRING}
        svc.speculator.start(normalize_messages(MSGS_STRING), fake_stream())
        got = await svc._create_message_stream(AsyncMock(), params)
        assert got == "PRESTARTED"

    async def test_miss_falls_through_to_real_call(self):
        svc = make_service()
        real_call = AsyncMock(return_value="REAL")
        got = await svc._create_message_stream(real_call, {"messages": MSGS_STRING})
        assert got == "REAL"
        real_call.assert_awaited_once()

    def test_build_params_carries_model_and_stream(self):
        from pipecat.processors.aggregators.llm_context import LLMContext

        svc = make_service()
        params = svc.build_request_params(LLMContext(messages=MSGS_STRING))
        assert params["model"] == "claude-haiku-4-5-20251001"
        assert params["stream"] is True
        assert params["max_tokens"] == 300
        assert "messages" in params
