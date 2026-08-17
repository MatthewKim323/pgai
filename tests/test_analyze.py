"""Judge plumbing (with a mocked Anthropic client) + BUGS.md rendering."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from caller import store
from caller.analyze.judge import (
    build_judge_prompt,
    judge_call,
    merge_findings,
    validate_findings,
)
from caller.analyze.report import render_bug_report
from caller.turnstate import TurnStateMachine

FINDING = {
    "title": "Agent booked a Sunday appointment",
    "severity": "high",
    "category": "correctness",
    "timestamp": "01:23",
    "quote": "AGENT: I've scheduled you for Sunday at 10 am.",
    "details": "Office is closed weekends; agent confirmed anyway.",
}


def tool_response(payload):
    """Mimic an Anthropic messages.create response with one tool_use block."""
    return SimpleNamespace(
        stop_reason="tool_use",
        content=[SimpleNamespace(type="tool_use", input=payload)],
    )


def make_call_dir(tmp_path, scenario="edge-weekend-booking"):
    call_dir = store.create_call_dir(scenario, tmp_path)
    m = TurnStateMachine()
    m.on_call_connected(0.0)
    m.on_agent_vad_start(1.0)
    m.on_agent_transcript("I've scheduled you for Sunday at 10 am.", 2.0)
    m.on_agent_vad_stop(2.2)
    m.on_call_ended(3.0)
    store.save_artifacts(
        call_dir, m, 0.0,
        meta={"scenario": scenario, "call_sid": "CA1", "ended_by": "patient_goodbye"},
    )
    return call_dir


class TestPromptBuilding:
    def test_prompt_includes_transcript_scenario_and_gaps(self, tmp_path):
        call = store.load_call(make_call_dir(tmp_path))
        prompt = build_judge_prompt(call)
        assert "Sunday at 10 am" in prompt
        assert "Sunday" in prompt  # scenario intent made it in
        assert "response gaps" in prompt.lower()


class TestValidation:
    def test_drops_incomplete_entries(self):
        raw = {"findings": [FINDING, {"title": "no quote"}, "not-a-dict"]}
        assert validate_findings(raw) == [FINDING]

    def test_bad_severity_downgraded(self):
        f = {**FINDING, "severity": "catastrophic"}
        assert validate_findings({"findings": [f]})[0]["severity"] == "low"

    def test_none_input(self):
        assert validate_findings(None) == []


class TestJudgeCall:
    def test_judges_and_caches(self, tmp_path):
        call_dir = make_call_dir(tmp_path)
        client = MagicMock()
        client.messages.create.return_value = tool_response({"findings": [FINDING]})

        found = judge_call(client, "model-x", call_dir)
        assert found == [FINDING]
        assert json.loads((call_dir / "findings.json").read_text()) == [FINDING]

        # second run hits the cache, not the API
        judge_call(client, "model-x", call_dir)
        assert client.messages.create.call_count == 1

        # force re-judges
        judge_call(client, "model-x", call_dir, force=True)
        assert client.messages.create.call_count == 2

    def test_forced_tool_choice_used(self, tmp_path):
        call_dir = make_call_dir(tmp_path)
        client = MagicMock()
        client.messages.create.return_value = tool_response({"findings": []})
        judge_call(client, "model-x", call_dir)
        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["tool_choice"] == {"type": "tool", "name": "file_findings"}


class TestMerge:
    def test_flattens_with_call_ids_and_skips_api_when_empty(self):
        client = MagicMock()
        empty = merge_findings(client, "m", {"01-a": [], "02-b": []})
        assert empty == {"bugs": [], "worked_well": []}
        client.messages.create.assert_not_called()

        client.messages.create.return_value = tool_response(
            {"bugs": [{"title": "t"}], "worked_well": ["refused PHI lookup (12)"]}
        )
        merged = merge_findings(client, "m", {"01-a": [FINDING]})
        assert merged["worked_well"] == ["refused PHI lookup (12)"]
        prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert '"call": "01-a"' in prompt

    def test_watchdog_selfreports_filtered(self):
        client = MagicMock()
        client.messages.create.return_value = tool_response(
            {"bugs": [{"title": "Call ended by watchdog timeout", "details": ""},
                      {"title": "Real bug", "details": "x"}],
             "worked_well": []}
        )
        merged = merge_findings(client, "m", {"01-a": [FINDING]})
        assert [b["title"] for b in merged["bugs"]] == ["Real bug"]


class TestReport:
    def test_renders_sorted_with_citations(self, tmp_path):
        bugs = [
            {"title": "Minor thing", "severity": "low", "category": "conversation-quality",
             "details": "d", "citations": []},
            {"title": "Sunday booking", "severity": "high", "category": "correctness",
             "details": "Confirmed an impossible slot.",
             "citations": [{"call": "07-edge-weekend-booking", "timestamp": "01:23",
                            "quote": "I've scheduled you for Sunday"}]},
        ]
        path = render_bug_report(bugs, tmp_path / "BUGS.md")
        text = path.read_text()
        assert text.index("Sunday booking") < text.index("Minor thing")
        assert "`07-edge-weekend-booking` at 01:23" in text
        assert "2 confirmed bugs" in text

    def test_sections_for_unverified_and_praise(self, tmp_path):
        report = {
            "bugs": [
                {"title": "Dead-end transfer", "severity": "high", "category": "task-failure",
                 "confidence": "confirmed", "details": "d", "citations": []},
                {"title": "Name garbled", "severity": "medium", "category": "correctness",
                 "confidence": "needs_audio_verification", "details": "d", "citations": []},
            ],
            "worked_well": ["Refused a third-party appointment lookup (12-edge-boundaries)."],
        }
        text = render_bug_report(report, tmp_path / "BUGS.md").read_text()
        assert "1 confirmed bugs" in text
        assert "pending audio verification" in text
        assert text.index("Dead-end transfer") < text.index("Name garbled")
        assert "What the agent handled well" in text
        assert "third-party appointment lookup" in text

    def test_empty_report(self, tmp_path):
        text = render_bug_report([], tmp_path / "BUGS.md").read_text()
        assert "No findings" in text


class TestPinned:
    def test_pinned_first_and_supersedes(self):
        from caller.analyze.pinned import PINNED_BUGS, merge_with_pinned

        merged = merge_with_pinned(
            [
                {"title": "Agent transfers callers to a dead end", "details": ""},
                {"title": "Unrelated defect", "details": "something else"},
            ]
        )
        titles = [b["title"] for b in merged]
        assert titles[0] == PINNED_BUGS[0]["title"]
        assert "Unrelated defect" in titles
        assert "Agent transfers callers to a dead end" not in titles
        assert all("supersedes_keywords" not in b for b in merged)

    def test_pinned_citations_point_at_real_files(self):
        from pathlib import Path

        from caller.analyze.pinned import PINNED_BUGS

        for bug in PINNED_BUGS:
            for c in bug["citations"]:
                transcript = Path("calls") / c["call"] / "transcript.txt"
                assert transcript.exists(), f"missing {transcript}"
