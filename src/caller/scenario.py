"""Scenario engine: YAML-defined patient personas and the prompts they become.

A scenario is one test call: who the patient is, how they talk, what they
want, and when the call should end. Scenarios live in `scenarios/*.yaml` so
adding coverage never means touching code.

Identity handling: scenarios for *existing-patient* flows set
`persona.registered: true`, which merges in `scenarios/identity.local.yaml`
(gitignored -- it holds the real identity registered with the Pretty Good AI
demo, which is personal data that does not belong in a public repo).
New-patient scenarios carry fictional inline identities.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from caller.turnstate import BargeInPolicy

SCENARIO_DIR = Path(__file__).resolve().parents[2] / "scenarios"
IDENTITY_FILE = "identity.local.yaml"

# How each behavior profile talks. Injected verbatim into the system prompt.
BEHAVIOR_PROFILES: dict[str, str] = {
    "baseline": (
        "You are polite, reasonably concise, and cooperative. You answer questions "
        "directly and stay on topic."
    ),
    "rambler": (
        "You are chatty and long-winded. You wrap answers in small personal stories "
        "(your garden, your grandkids, the weather) before getting to the point. You are "
        "warm and never rude, just slow to land the plane. Still answer what was asked, "
        "eventually."
    ),
    "interrupter": (
        "You are impatient and in a hurry. You talk in quick bursts, sometimes cut in "
        "before the other person finishes, and push for fast answers. You are brusque "
        "but not abusive."
    ),
    "confused": (
        "You are easily confused. You mishear details, ask for things to be repeated, "
        "change your mind mid-call, and occasionally contradict something you said "
        "earlier. You mean well and appreciate patience."
    ),
    "topic_switcher": (
        "You start with one request but keep pivoting to unrelated questions mid-flow "
        "(billing, parking, a different family member's appointment) before circling "
        "back. Each pivot should feel natural, not random."
    ),
}


class ScenarioError(ValueError):
    """A scenario file is missing or malformed."""


@dataclass(frozen=True)
class Persona:
    first_name: str
    last_name: str
    dob: date | None = None
    phone: str | None = None
    insurance: str | None = None
    medications: tuple[str, ...] = ()
    background: str = ""
    voice_id: str | None = None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def dob_spoken(self) -> str | None:
        """DOB as a human says it on the phone ('March 23rd, 2006')."""
        if self.dob is None:
            return None
        day = self.dob.day
        suffix = "th" if 11 <= day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        return f"{self.dob.strftime('%B')} {day}{suffix}, {self.dob.year}"


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    category: str
    persona: Persona
    goal: str
    behavior: str = "baseline"
    barge_in_policy: BargeInPolicy = BargeInPolicy.YIELD
    steering: tuple[str, ...] = ()
    max_minutes: float = 3.0
    uses_registered_identity: bool = False


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text())
    except FileNotFoundError:
        raise ScenarioError(f"scenario file not found: {path}") from None
    except yaml.YAMLError as e:
        raise ScenarioError(f"invalid YAML in {path}: {e}") from None
    if not isinstance(data, dict):
        raise ScenarioError(f"{path} must be a YAML mapping")
    return data


def _parse_dob(raw: Any, source: Path) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        raise ScenarioError(f"{source}: dob must be YYYY-MM-DD, got {raw!r}") from None


def _build_persona(spec: dict[str, Any], source: Path, scenario_dir: Path) -> tuple[Persona, bool]:
    registered = bool(spec.get("registered", False))
    if registered:
        identity_path = scenario_dir / IDENTITY_FILE
        if not identity_path.exists():
            raise ScenarioError(
                f"{source} needs the registered identity, but {identity_path} is missing. "
                f"Copy scenarios/identity.example.yaml and fill in the details used at signup."
            )
        # Registered identity provides the base; the scenario may still override
        # scenario-specific fields (background, medications, voice).
        spec = {**_load_yaml(identity_path), **{k: v for k, v in spec.items() if k != "registered"}}

    missing = [k for k in ("first_name", "last_name") if not spec.get(k)]
    if missing:
        raise ScenarioError(f"{source}: persona is missing {', '.join(missing)}")

    persona = Persona(
        first_name=str(spec["first_name"]),
        last_name=str(spec["last_name"]),
        dob=_parse_dob(spec.get("dob"), source),
        phone=str(spec["phone"]) if spec.get("phone") else None,
        insurance=spec.get("insurance"),
        medications=tuple(spec.get("medications", ())),
        background=str(spec.get("background", "")).strip(),
        voice_id=spec.get("voice_id"),
    )
    return persona, registered


def load_scenario(scenario_id: str, scenario_dir: Path = SCENARIO_DIR) -> Scenario:
    path = scenario_dir / f"{scenario_id}.yaml"
    data = _load_yaml(path)

    for key in ("id", "title", "category", "persona", "goal"):
        if key not in data:
            raise ScenarioError(f"{path}: missing required key '{key}'")
    if data["id"] != scenario_id:
        raise ScenarioError(f"{path}: id '{data['id']}' does not match filename")

    behavior = data.get("behavior", "baseline")
    if behavior not in BEHAVIOR_PROFILES:
        raise ScenarioError(
            f"{path}: unknown behavior '{behavior}' (valid: {', '.join(BEHAVIOR_PROFILES)})"
        )

    try:
        barge = BargeInPolicy(data.get("barge_in_policy", "yield"))
    except ValueError:
        raise ScenarioError(f"{path}: barge_in_policy must be 'yield' or 'hold'") from None

    persona, registered = _build_persona(dict(data["persona"]), path, scenario_dir)

    return Scenario(
        id=data["id"],
        title=str(data["title"]),
        category=str(data["category"]),
        persona=persona,
        goal=str(data["goal"]).strip(),
        behavior=behavior,
        barge_in_policy=barge,
        steering=tuple(data.get("steering", ())),
        max_minutes=float(data.get("max_minutes", 3.0)),
        uses_registered_identity=registered,
    )


def list_scenarios(scenario_dir: Path = SCENARIO_DIR) -> list[str]:
    return sorted(
        p.stem
        for p in scenario_dir.glob("*.yaml")
        if p.name not in (IDENTITY_FILE, "identity.example.yaml")
    )


def build_system_prompt(scenario: Scenario, practice_name: str = "Pivot Point Orthopedics") -> str:
    """The patient brain's system prompt: identity + voice discipline + goal."""
    p = scenario.persona

    identity_lines = [f"Your name is {p.full_name}."]
    if p.dob:
        identity_lines.append(
            f"Your date of birth is {p.dob.isoformat()} -- say it naturally, "
            f'as "{p.dob_spoken()}".'
        )
    if p.phone:
        identity_lines.append(f"Your phone number is {p.phone}.")
    if p.insurance:
        identity_lines.append(f"Your insurance is {p.insurance}.")
    if p.medications:
        identity_lines.append(f"Your current medications: {', '.join(p.medications)}.")
    if p.background:
        identity_lines.append(f"Background: {p.background}")

    steering_block = ""
    if scenario.steering:
        steering_block = "Steering notes:\n" + "\n".join(f"- {s}" for s in scenario.steering)

    return f"""You are {p.full_name}, a real person making a phone call to {practice_name}. \
You are the CALLER; the receptionist answers. Never break character. You are not an AI and \
no one must ever suspect you are.

WHO YOU ARE
{chr(10).join(identity_lines)}

HOW YOU SPEAK
This is a live phone call, so sound like one:
- Short, natural sentences with contractions. One conversational beat per reply.
- Occasional light fillers ("um", "sure", "let's see") -- sparingly, not every turn.
- Never use lists, headings, stage directions, emoji, or parentheticals. Plain spoken words only.
- Say numbers, dates, and times the way people say them out loud.
- If you didn't catch something, ask them to repeat it, like a person would.
- Answer verification questions (name, date of birth, phone) with your details above. If asked \
something about yourself not listed, improvise a brief, plausible answer and stay consistent \
with it for the rest of the call.

{BEHAVIOR_PROFILES[scenario.behavior]}

YOUR GOAL
{scenario.goal}
{steering_block}

Steer the conversation toward your goal. If the receptionist drifts or stalls, politely bring \
it back. Confirm important details back (dates, times, locations) the way a careful patient \
would.

ENDING THE CALL
The moment your goal is achieved, or it is clearly impossible, wrap up: thank them, say \
goodbye, and then call the end_call tool. Do not invent extra questions once you have what \
you came for -- real callers hang up. Never just go silent, and never call end_call without \
saying goodbye first."""
