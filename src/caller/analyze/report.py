"""Render the merged findings into BUGS.md, the challenge deliverable."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ORDER = {"high": 0, "medium": 1, "low": 2}
_LABEL = {"high": "High", "medium": "Medium", "low": "Low"}


def render_bug_report(bugs: list[dict[str, Any]], path: Path = Path("BUGS.md")) -> Path:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    lines = [
        "# Bug report",
        "",
        f"Findings from automated test calls against the Pretty Good AI agent ({stamp}).",
        "Each bug cites the call directory under `calls/` and a transcript timestamp;",
        "the mm:ss positions line up with `transcript.txt` and `recording.mp3`.",
        "",
    ]

    if not bugs:
        lines += ["No findings on record yet. Run `python -m caller analyze` after some calls."]
    else:
        counts = {sev: sum(1 for b in bugs if b.get("severity") == sev) for sev in _ORDER}
        lines += [
            f"**{len(bugs)} bugs** -- "
            + ", ".join(f"{counts[s]} {s}" for s in _ORDER if counts[s]),
            "",
        ]
        for i, bug in enumerate(
            sorted(bugs, key=lambda b: _ORDER.get(b.get("severity", "low"), 3)), start=1
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

    path.write_text("\n".join(lines).rstrip() + "\n")
    return path
