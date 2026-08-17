"""Cross-call knowledge: the campaign learns the practice as it calls.

After each call, a cheap extraction pass mines the transcript for two kinds
of knowledge, accumulated in calls/knowledge.json:

* **practice facts** -- things a real patient could plausibly know or have
  heard (provider names, hours, policies). Later personas get these as
  natural background ("a friend of yours goes to this practice"), which makes
  the calls more grounded AND lets them test the agent against its own
  earlier claims.
* **leads** -- suspicious behaviors worth another probe (transfers that dead
  end, questions that get dodged). Leads become steering suggestions for
  later calls, phrased as ordinary caller intentions so the persona never
  breaks character by knowing things a patient couldn't.

Static scenarios make the first calls reproducible; knowledge makes the
later ones adaptive. Both postures are deliberate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anthropic
from loguru import logger

from caller import store

KNOWLEDGE_FILE = "knowledge.json"

EXTRACT_TOOL = {
    "name": "file_knowledge",
    "description": "File what this call revealed about the practice and its phone agent.",
    "input_schema": {
        "type": "object",
        "properties": {
            "practice_facts": {
                "type": "array",
                "description": (
                    "Concrete facts about the practice a patient could plausibly know or "
                    "repeat: provider names, hours, locations, stated policies. Short, "
                    "declarative, one fact each. Empty if none."
                ),
                "items": {"type": "string"},
            },
            "leads": {
                "type": "array",
                "description": (
                    "Suspicious agent behaviors worth re-testing on a future call, phrased "
                    "as an actionable caller move, e.g. 'asking to be transferred appears "
                    "to reach a dead end -- accept a transfer offer and see what happens'. "
                    "Empty if none."
                ),
                "items": {"type": "string"},
            },
        },
        "required": ["practice_facts", "leads"],
    },
}

EXTRACT_SYSTEM = """You are maintaining the shared memory of a QA campaign that phone-tests \
an AI receptionist. Given one call transcript, extract only NEW, concrete, reusable \
knowledge. No speculation, no duplicates of the already-known list, no nitpicks. Facts must \
be things the agent actually said."""


def load(calls_dir: Path = store.CALLS_DIR) -> dict[str, list[dict[str, Any]]]:
    path = calls_dir / KNOWLEDGE_FILE
    if not path.exists():
        return {"practice_facts": [], "leads": []}
    return json.loads(path.read_text())


def _save(knowledge: dict[str, Any], calls_dir: Path) -> None:
    calls_dir.mkdir(parents=True, exist_ok=True)
    (calls_dir / KNOWLEDGE_FILE).write_text(json.dumps(knowledge, indent=2) + "\n")


def update_from_call(
    client: anthropic.Anthropic,
    model: str,
    call_dir: Path,
    calls_dir: Path = store.CALLS_DIR,
) -> dict[str, Any]:
    """Mine one finished call and fold what it revealed into the shared memory."""
    call = store.load_call(call_dir)
    if not call["transcript_text"].strip():
        return load(calls_dir)

    knowledge = load(calls_dir)
    known = [f["text"] for f in knowledge["practice_facts"]] + [
        f["text"] for f in knowledge["leads"]
    ]
    prompt = (
        "Already known (do NOT repeat):\n"
        + (json.dumps(known, indent=1) if known else "(nothing yet)")
        + f"\n\nTranscript of call {call['id']}:\n{call['transcript_text']}\n\n"
        "File the new knowledge now."
    )
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        system=EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        tools=[EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "file_knowledge"},
    )
    raw = next((b.input for b in resp.content if b.type == "tool_use"), {})

    existing = {f["text"] for k in knowledge.values() for f in k}
    added = 0
    for kind in ("practice_facts", "leads"):
        for text in raw.get(kind, []):
            text = str(text).strip()
            if text and text not in existing:
                knowledge[kind].append({"text": text, "source": call_dir.name})
                existing.add(text)
                added += 1
    _save(knowledge, calls_dir)
    logger.info(f"{call_dir.name}: knowledge updated (+{added})")
    return knowledge


def prompt_block(knowledge: dict[str, Any], max_items: int = 6) -> str:
    """Render accumulated knowledge into persona-safe prompt text.

    Facts arrive as plausible hearsay; leads arrive as the caller's own idle
    intentions. The persona never learns anything a patient couldn't know.
    """
    facts = [f["text"] for f in knowledge.get("practice_facts", [])][-max_items:]
    leads = [f["text"] for f in knowledge.get("leads", [])][-max_items:]
    if not facts and not leads:
        return ""

    parts = []
    if facts:
        parts.append(
            "Things you happen to know about this practice (a friend of yours is a patient "
            "there and mentioned them; bring them up only when natural):\n"
            + "\n".join(f"- {t}" for t in facts)
        )
    if leads:
        parts.append(
            "If the conversation drifts there naturally (never force it, and never explain "
            "why), you're inclined to:\n" + "\n".join(f"- {t}" for t in leads)
        )
    return "\n\n".join(parts)
