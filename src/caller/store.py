"""Call artifact store: one directory per call, everything a reviewer needs.

calls/
  03-refill/
    meta.json        scenario, call sid, timing, how the call ended
    transcript.txt   the human-readable transcript the bug report cites
    transcript.json  same, structured
    timeline.json    every turn-state event
    telemetry.json   per-turn latency (ours) + response gaps (theirs)
    recording.mp3    dual-channel audio, agent left / patient right

Directories are numbered in call order so "transcript-03" means something.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from caller import telemetry, transcript
from caller.turnstate import TurnStateMachine

CALLS_DIR = Path("calls")


def _next_index(calls_dir: Path) -> int:
    highest = 0
    for p in calls_dir.glob("[0-9][0-9]-*"):
        m = re.match(r"^(\d+)-", p.name)
        if m:
            highest = max(highest, int(m.group(1)))
    return highest + 1


def create_call_dir(scenario_id: str, calls_dir: Path = CALLS_DIR) -> Path:
    calls_dir.mkdir(parents=True, exist_ok=True)
    path = calls_dir / f"{_next_index(calls_dir):02d}-{scenario_id}"
    path.mkdir()
    return path


def save_artifacts(
    call_dir: Path,
    machine: TurnStateMachine,
    call_start_ts: float | None,
    meta: dict[str, Any],
) -> None:
    """Write every text artifact for a completed call."""
    start = call_start_ts if call_start_ts is not None else (
        machine.events[0].ts if machine.events else 0.0
    )
    entries = transcript.from_events(machine.events, call_start_ts=start)

    (call_dir / "transcript.txt").write_text(transcript.to_text(entries) + "\n")
    _write_json(call_dir / "transcript.json", transcript.to_json(entries))
    _write_json(call_dir / "timeline.json", machine.timeline())
    _write_json(call_dir / "telemetry.json", telemetry.build_report(machine.turns, machine.events))
    _write_json(
        call_dir / "meta.json",
        {"saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **meta},
    )


def load_call(call_dir: Path) -> dict[str, Any]:
    """Read a call's artifacts back (dashboard + judge input)."""
    out: dict[str, Any] = {"id": call_dir.name, "dir": str(call_dir)}
    for name in ("meta", "transcript", "timeline", "telemetry"):
        f = call_dir / f"{name}.json"
        out[name] = json.loads(f.read_text()) if f.exists() else None
    txt = call_dir / "transcript.txt"
    out["transcript_text"] = txt.read_text() if txt.exists() else ""
    mp3 = call_dir / "recording.mp3"
    out["recording"] = mp3.name if mp3.exists() else None
    return out


def list_calls(calls_dir: Path = CALLS_DIR) -> list[Path]:
    if not calls_dir.exists():
        return []
    return sorted(p for p in calls_dir.iterdir() if p.is_dir() and re.match(r"^\d+-", p.name))


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")
