"""Per-turn latency telemetry, derived from the turn-state machine's record.

Two families of numbers, deliberately kept separate:

* **Patient-side** (our bot's performance): how fast we respond after the
  agent stops talking. This is what we tune -- it decides whether the call
  sounds like a human or like dead air.
* **Agent-side** (the system under test): how long the agent leaves us
  hanging after we finish speaking. Long gaps here are *findings*, and feed
  the bug report.
"""

from __future__ import annotations

from statistics import median
from typing import Any

from caller.turnstate import EV_STATE, CallState, StateEvent, Turn


def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, max(0, round(q * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


def _summary(vals: list[float]) -> dict[str, float] | None:
    if not vals:
        return None
    s = sorted(vals)
    return {
        "count": len(s),
        "p50": round(median(s), 3),
        "p95": round(_percentile(s, 0.95), 3),
        "max": round(s[-1], 3),
        "mean": round(sum(s) / len(s), 3),
    }


def patient_turn_metrics(turns: list[Turn]) -> list[dict[str, Any]]:
    """One row per completed exchange: our think + speak latencies."""
    rows: list[dict[str, Any]] = []
    for t in turns:
        if t.agent_stop_ts is None:
            continue
        row: dict[str, Any] = {"turn": t.index, "interrupted": t.interrupted}
        if t.llm_first_token_ts is not None:
            row["llm_first_token"] = round(t.llm_first_token_ts - t.agent_stop_ts, 3)
        if t.tts_first_audio_ts is not None:
            row["response_latency"] = round(t.tts_first_audio_ts - t.agent_stop_ts, 3)
        if t.patient_stop_ts is not None and t.tts_first_audio_ts is not None:
            row["speech_duration"] = round(t.patient_stop_ts - t.tts_first_audio_ts, 3)
        rows.append(row)
    return rows


def agent_response_gaps(events: list[StateEvent]) -> list[float]:
    """How long the agent left us waiting: gaps between us finishing a turn
    (state -> waiting_greeting) and the agent starting to speak again."""
    gaps: list[float] = []
    waiting_since: float | None = None
    for ev in events:
        if ev.type != EV_STATE:
            continue
        to = ev.data.get("to")
        if to == CallState.WAITING_GREETING.value:
            waiting_since = ev.ts
        elif to == CallState.AGENT_SPEAKING.value and waiting_since is not None:
            gaps.append(round(ev.ts - waiting_since, 3))
            waiting_since = None
        elif to == CallState.ENDED.value:
            waiting_since = None
    return gaps


def build_report(turns: list[Turn], events: list[StateEvent]) -> dict[str, Any]:
    """The telemetry.json artifact for one call."""
    per_turn = patient_turn_metrics(turns)
    gaps = agent_response_gaps(events)
    call_span = (events[-1].ts - events[0].ts) if len(events) >= 2 else 0.0
    return {
        "call_duration_secs": round(call_span, 3),
        "completed_turns": len(per_turn),
        "interruptions": sum(1 for t in turns if t.interrupted),
        "patient": {
            "per_turn": per_turn,
            "response_latency": _summary(
                [r["response_latency"] for r in per_turn if "response_latency" in r]
            ),
            "llm_first_token": _summary(
                [r["llm_first_token"] for r in per_turn if "llm_first_token" in r]
            ),
        },
        "agent_under_test": {
            "response_gaps": gaps,
            "response_gap": _summary(gaps),
        },
    }
