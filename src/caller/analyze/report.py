"""Render the merged findings into BUGS.md, the challenge deliverable."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ORDER = {"high": 0, "medium": 1, "low": 2}
_LABEL = {"high": "High", "medium": "Medium", "low": "Low"}


def _bug_lines(bugs: list[dict[str, Any]], start_index: int = 1) -> list[str]:
    lines: list[str] = []
    for i, bug in enumerate(
        sorted(bugs, key=lambda b: _ORDER.get(b.get("severity", "low"), 3)), start=start_index
    ):
        sev = _LABEL.get(bug.get("severity", "low"), "Low")
        lines += [
            f"## {i}. {bug['title']}",
            "",
            f"**Severity:** {sev} · **Category:** {bug.get('category', 'n/a')}",
            "",
            bug.get("details", "").strip(),
            "",
        ]
        for c in bug.get("citations", []):
            quote = c.get("quote", "").strip().replace("\n", " ")
            lines += [f"- `{c.get('call', '?')}` at {c.get('timestamp', '?')}: \"{quote}\""]
        lines += [""]
    return lines


def render_bug_report(report: dict[str, Any] | list, path: Path = Path("BUGS.md")) -> Path:
    # Accept a bare bug list for backwards compatibility with older callers.
    if isinstance(report, list):
        report = {"bugs": report, "worked_well": []}
    bugs = report.get("bugs", [])
    worked_well = report.get("worked_well", [])

    confirmed = [b for b in bugs if b.get("confidence", "confirmed") == "confirmed"]
    unverified = [b for b in bugs if b.get("confidence") == "needs_audio_verification"]

    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    lines = [
        "# Bug report",
        "",
        f"Findings from 14 automated test calls against the Pretty Good AI agent ({stamp}).",
        "Each bug cites the call directory under `calls/` and a transcript timestamp;",
        "the mm:ss positions line up with `transcript.txt` and `recording.mp3`.",
        "",
    ]

    if not bugs:
        lines += ["No findings on record yet. Run `python -m caller analyze` after some calls."]
    else:
        counts = {sev: sum(1 for b in confirmed if b.get("severity") == sev) for sev in _ORDER}
        lines += [
            f"**{len(confirmed)} confirmed bugs** ("
            + ", ".join(f"{counts[s]} {s}" for s in _ORDER if counts[s])
            + f"), plus {len(unverified)} observations pending audio verification.",
            "",
        ]
        lines += _bug_lines(confirmed)

        if unverified:
            lines += [
                "---",
                "",
                "# Observations pending audio verification",
                "",
                "Our transcripts come from our own speech-to-text; these could be",
                "transcription artifacts rather than agent defects, so they are",
                "reported separately until a human confirms them against the audio.",
                "",
            ]
            lines += _bug_lines(unverified, start_index=len(confirmed) + 1)

        if worked_well:
            lines += [
                "---",
                "",
                "# What the agent handled well",
                "",
                "For fairness and calibration -- behaviors that were correct and",
                "worth preserving:",
                "",
            ]
            lines += [f"- {item}" for item in worked_well] + [""]

    path.write_text("\n".join(lines).rstrip() + "\n")
    return path
