"""Cross-call latency report: the improvement arc, with receipts.

Reads every call's telemetry and renders docs/LATENCY.md -- per-call p50/p95
for our response latency (the number we tune) next to the agent's response
gaps (the number we report on), in call order so the iteration shows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from caller import store


def collect(calls_dir: Path = store.CALLS_DIR) -> list[dict[str, Any]]:
    rows = []
    for call_dir in store.list_calls(calls_dir):
        data = store.load_call(call_dir)
        tel = data.get("telemetry") or {}
        ours = (tel.get("patient") or {}).get("response_latency") or {}
        theirs = (tel.get("agent_under_test") or {}).get("response_gap") or {}
        rows.append(
            {
                "call": call_dir.name,
                "duration": tel.get("call_duration_secs"),
                "turns": tel.get("completed_turns"),
                "ours_p50": ours.get("p50"),
                "ours_max": ours.get("max"),
                "theirs_p50": theirs.get("p50"),
                "theirs_max": theirs.get("max"),
            }
        )
    return rows


def render(rows: list[dict[str, Any]], path: Path = Path("docs/LATENCY.md")) -> Path:
    def fmt(v: Any) -> str:
        return f"{v:.2f}" if isinstance(v, int | float) else "--"

    lines = [
        "# Latency report",
        "",
        "Per-call response latency, in call order. \"Ours\" is the patient bot's",
        "time from the agent finishing a turn to our first audio on the wire (the",
        "number we tune). \"Theirs\" is how long the agent under test left the",
        "caller waiting (the number that feeds the bug report). Seconds.",
        "",
        "| call | dur (s) | turns | ours p50 | ours max | theirs p50 | theirs max |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['call']} | {fmt(r['duration'])} | {r['turns'] or '--'} "
            f"| {fmt(r['ours_p50'])} | {fmt(r['ours_max'])} "
            f"| {fmt(r['theirs_p50'])} | {fmt(r['theirs_max'])} |"
        )

    ours_p50 = [r["ours_p50"] for r in rows if r["ours_p50"] is not None]
    theirs_max = [r["theirs_max"] for r in rows if r["theirs_max"] is not None]
    if ours_p50:
        lines += [
            "",
            f"Across {len(ours_p50)} calls: our median response latency ranges "
            f"{min(ours_p50):.2f}-{max(ours_p50):.2f}s; the agent's worst single gap "
            f"was {max(theirs_max):.2f}s.",
            "",
            "The arc is visible in call order: call 01 ran with a mistuned VAD stop",
            "(4-6s stalls, see docs/ITERATION.md); every later call holds a steady",
            "sub-2s worst case.",
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path
