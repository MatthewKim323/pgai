"""Two-party transcript assembly.

We only run STT on inbound audio (the agent under test); the patient's words
are the LLM's committed utterances, which we already have as text. Both are
recorded as timestamped turn-state events, so the transcript is a projection
of the event timeline -- no separate bookkeeping that can drift out of sync.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from caller.turnstate import EV_AGENT_SAID, EV_PATIENT_SAID, StateEvent

AGENT = "agent"
PATIENT = "patient"

#: consecutive same-speaker segments closer than this merge into one line
MERGE_GAP_SECS = 2.0


@dataclass
class Entry:
    speaker: str
    text: str
    ts: float  # seconds since call start
    end_ts: float


def from_events(events: list[StateEvent], call_start_ts: float = 0.0) -> list[Entry]:
    """Project speech events into merged, ordered transcript entries."""
    entries: list[Entry] = []
    for ev in events:
        if ev.type == EV_AGENT_SAID:
            speaker = AGENT
        elif ev.type == EV_PATIENT_SAID:
            speaker = PATIENT
        else:
            continue
        ts = ev.ts - call_start_ts
        text = ev.data["text"]
        prev = entries[-1] if entries else None
        if prev and prev.speaker == speaker and ts - prev.end_ts <= MERGE_GAP_SECS:
            prev.text = f"{prev.text} {text}"
            prev.end_ts = ts
        else:
            entries.append(Entry(speaker=speaker, text=text, ts=ts, end_ts=ts))
    return entries


def _stamp(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def to_text(entries: list[Entry]) -> str:
    """Human-readable transcript with mm:ss timestamps.

    This is the format cited by the bug report ('transcript-03.txt at 1:23').
    """
    return "\n".join(f"[{_stamp(e.ts)}] {e.speaker.upper()}: {e.text}" for e in entries)


def to_json(entries: list[Entry]) -> list[dict[str, Any]]:
    return [
        {"speaker": e.speaker, "text": e.text, "ts": round(e.ts, 3), "stamp": _stamp(e.ts)}
        for e in entries
    ]
