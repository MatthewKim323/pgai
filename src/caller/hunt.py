"""Lead hunting: the harness writes its own final test case.

Static scenarios cover the known surface; the knowledge store accumulates
what they flushed out. `hunt` closes the loop -- an LLM reads the open leads
and authors a brand-new scenario YAML (fresh persona, goal, steering) built
to corner the most promising one. The generated file goes through the same
loader and validation as the hand-written scenarios, then runs like any
other call.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import anthropic
import yaml
from loguru import logger

from caller.scenario import SCENARIO_DIR, load_scenario

#: voices the generator may assign, so hunts sound like new callers
HUNT_VOICES = [
    "aura-2-andromeda-en",
    "aura-2-helena-en",
    "aura-2-atlas-en",
    "aura-2-aurora-en",
]

HUNT_TOOL = {
    "name": "file_scenario",
    "description": "File the generated test-call scenario.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "first_name": {"type": "string"},
            "last_name": {"type": "string"},
            "dob": {"type": "string", "description": "YYYY-MM-DD"},
            "phone": {"type": "string", "description": "10 digits, use a 555 exchange"},
            "insurance": {"type": "string"},
            "background": {"type": "string", "description": "who this caller is, 1-2 sentences"},
            "goal": {
                "type": "string",
                "description": (
                    "what the caller wants, written to naturally corner the targeted lead(s); "
                    "never mentions testing, bugs, or prior calls"
                ),
            },
            "steering": {"type": "array", "items": {"type": "string"}},
            "targeted_leads": {
                "type": "array",
                "items": {"type": "string"},
                "description": "the lead(s) this scenario is built to probe, verbatim",
            },
        },
        "required": [
            "title", "first_name", "last_name", "dob", "phone",
            "insurance", "background", "goal", "steering", "targeted_leads",
        ],
    },
}

HUNT_SYSTEM = """You design test calls for a QA campaign against an AI phone receptionist \
at an orthopedics practice. Given open leads (suspicious behaviors from earlier calls), \
author ONE new patient scenario engineered to corner the most promising lead -- or two if \
they combine naturally.

Rules:
- The persona is an ordinary, believable patient. The goal and steering must read as normal \
patient intentions; the caller can never reference testing, bugs, or other calls.
- Pick the lead(s) with the highest potential severity (data integrity, dead ends, safety) \
over cosmetic ones.
- Steering notes are concrete conversational moves, not abstractions.
- Fresh fictional identity, 555 phone number, plausible DOB for the persona's age."""


def _next_hunt_id(scenario_dir: Path) -> str:
    nums = [
        int(m.group(1))
        for p in scenario_dir.glob("hunt-*.yaml")
        if (m := re.match(r"hunt-(\d+)$", p.stem))
    ]
    return f"hunt-{max(nums, default=0) + 1}"


def generate_hunt(
    client: anthropic.Anthropic,
    model: str,
    knowledge: dict[str, Any],
    scenario_dir: Path = SCENARIO_DIR,
) -> str:
    """Author, validate, and save a lead-hunting scenario. Returns its id."""
    leads = [f["text"] for f in knowledge.get("leads", [])]
    if not leads:
        raise ValueError("no leads in the knowledge store; nothing to hunt")
    facts = [f["text"] for f in knowledge.get("practice_facts", [])]

    prompt = (
        "Open leads:\n" + "\n".join(f"- {t}" for t in leads)
        + "\n\nKnown practice facts (the persona may use these as hearsay):\n"
        + "\n".join(f"- {t}" for t in facts)
        + "\n\nFile the scenario now."
    )
    resp = client.messages.create(
        model=model,
        max_tokens=2048,
        system=HUNT_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        tools=[HUNT_TOOL],
        tool_choice={"type": "tool", "name": "file_scenario"},
    )
    spec = next((b.input for b in resp.content if b.type == "tool_use"), None)
    if not spec:
        raise RuntimeError("scenario generator returned no tool call")
    core = ("title", "first_name", "last_name", "dob", "phone", "insurance", "goal")
    missing = [k for k in core if not spec.get(k)]
    if missing:
        raise RuntimeError(f"scenario generator omitted required fields: {', '.join(missing)}")

    hunt_id = _next_hunt_id(scenario_dir)
    doc = {
        "id": hunt_id,
        "title": spec["title"],
        "category": "hunt",
        "persona": {
            "voice_id": HUNT_VOICES[(max(0, int(hunt_id.split('-')[1]) - 1)) % len(HUNT_VOICES)],
            "first_name": spec["first_name"],
            "last_name": spec["last_name"],
            "dob": spec["dob"],
            "phone": spec["phone"],
            "insurance": spec["insurance"],
            "background": spec.get("background", ""),
        },
        "goal": spec["goal"],
        "steering": list(spec.get("steering", [])),
        "max_minutes": 3,
        # provenance: which leads this scenario was authored to corner
        "targeted_leads": list(spec.get("targeted_leads", [])),
    }
    path = scenario_dir / f"{hunt_id}.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))

    try:
        load_scenario(hunt_id, scenario_dir)  # same validation as hand-written scenarios
    except Exception:
        path.unlink()  # never leave an unloadable scenario behind
        raise

    logger.info(f"generated {path} targeting: {'; '.join(doc['targeted_leads'])}")
    return hunt_id
