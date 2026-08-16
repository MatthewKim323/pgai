"""Scenario engine: loading, validation, identity merging, prompt building."""

from pathlib import Path

import pytest

from caller.scenario import (
    SCENARIO_DIR,
    Persona,
    Scenario,
    ScenarioError,
    build_system_prompt,
    list_scenarios,
    load_scenario,
)
from caller.turnstate import BargeInPolicy

IDENTITY = """\
first_name: Jane
last_name: Doe
dob: 1990-01-31
phone: "5551234567"
insurance: Blue Shield PPO
"""


def write(dirpath: Path, name: str, text: str) -> None:
    (dirpath / name).write_text(text)


@pytest.fixture
def sdir(tmp_path: Path) -> Path:
    write(
        tmp_path,
        "basic.yaml",
        """\
id: basic
title: Basic call
category: scheduling
persona:
  first_name: Diane
  last_name: Okafor
  dob: 1971-06-14
  medications: [meloxicam 15mg]
goal: Book an appointment.
steering:
  - Pick the earliest slot.
""",
    )
    return tmp_path


class TestLoading:
    def test_basic_fields(self, sdir: Path):
        s = load_scenario("basic", sdir)
        assert s.title == "Basic call"
        assert s.persona.full_name == "Diane Okafor"
        assert s.persona.medications == ("meloxicam 15mg",)
        assert s.barge_in_policy is BargeInPolicy.YIELD
        assert not s.uses_registered_identity

    def test_missing_file(self, sdir: Path):
        with pytest.raises(ScenarioError, match="not found"):
            load_scenario("nope", sdir)

    def test_missing_required_key(self, sdir: Path):
        write(sdir, "broken.yaml", "id: broken\ntitle: x\n")
        with pytest.raises(ScenarioError, match="missing required key"):
            load_scenario("broken", sdir)

    def test_id_filename_mismatch(self, sdir: Path):
        write(
            sdir,
            "mismatch.yaml",
            "id: other\ntitle: x\ncategory: c\npersona: {first_name: A, last_name: B}\ngoal: g\n",
        )
        with pytest.raises(ScenarioError, match="does not match filename"):
            load_scenario("mismatch", sdir)

    def test_unknown_behavior_rejected(self, sdir: Path):
        write(
            sdir,
            "bad.yaml",
            "id: bad\ntitle: x\ncategory: c\npersona: {first_name: A, last_name: B}\n"
            "goal: g\nbehavior: aggressive\n",
        )
        with pytest.raises(ScenarioError, match="unknown behavior"):
            load_scenario("bad", sdir)

    def test_bad_dob_rejected(self, sdir: Path):
        write(
            sdir,
            "bd.yaml",
            "id: bd\ntitle: x\ncategory: c\n"
            "persona: {first_name: A, last_name: B, dob: 14/06/1971}\ngoal: g\n",
        )
        with pytest.raises(ScenarioError, match="YYYY-MM-DD"):
            load_scenario("bd", sdir)


class TestRegisteredIdentity:
    def _registered_scenario(self, sdir: Path) -> None:
        write(
            sdir,
            "reg.yaml",
            """\
id: reg
title: Registered patient call
category: refills
persona:
  registered: true
  medications: [celecoxib 200mg]
  background: Last visit two weeks ago.
goal: Get a refill.
""",
        )

    def test_merges_identity_file(self, sdir: Path):
        self._registered_scenario(sdir)
        write(sdir, "identity.local.yaml", IDENTITY)
        s = load_scenario("reg", sdir)
        assert s.persona.full_name == "Jane Doe"
        assert s.persona.dob.isoformat() == "1990-01-31"
        # scenario-level fields still win / augment
        assert s.persona.medications == ("celecoxib 200mg",)
        assert s.uses_registered_identity

    def test_missing_identity_file_is_actionable(self, sdir: Path):
        self._registered_scenario(sdir)
        with pytest.raises(ScenarioError, match="identity.example.yaml"):
            load_scenario("reg", sdir)


class TestListing:
    def test_identity_files_excluded(self, sdir: Path):
        write(sdir, "identity.local.yaml", IDENTITY)
        write(sdir, "identity.example.yaml", IDENTITY)
        assert list_scenarios(sdir) == ["basic"]


class TestPromptBuilding:
    def test_prompt_carries_identity_and_goal(self, sdir: Path):
        s = load_scenario("basic", sdir)
        prompt = build_system_prompt(s)
        assert "Diane Okafor" in prompt
        assert "June 14th, 1971" in prompt
        assert "Book an appointment." in prompt
        assert "Pick the earliest slot." in prompt
        assert "end_call" in prompt

    def test_prompt_has_voice_discipline(self, sdir: Path):
        prompt = build_system_prompt(load_scenario("basic", sdir))
        assert "phone call" in prompt
        assert "Never use lists" in prompt

    def test_dob_suffixes(self):
        cases = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 11: "11th", 12: "12th", 21: "21st"}
        from datetime import date

        for day, expect in cases.items():
            p = Persona(first_name="A", last_name="B", dob=date(2000, 5, day))
            assert p.dob_spoken().startswith(f"May {expect}")


class TestRealScenarioLibrary:
    """The committed scenario files must all load (registered ones excepted
    when the local identity is absent) and cover the challenge's categories."""

    def test_all_committed_scenarios_parse(self):
        identity_present = (SCENARIO_DIR / "identity.local.yaml").exists()
        categories = set()
        for sid in list_scenarios():
            try:
                s = load_scenario(sid)
            except ScenarioError as e:
                if not identity_present and "identity" in str(e):
                    continue
                raise
            assert isinstance(s, Scenario)
            assert s.goal
            categories.add(s.category)
        # fictional-persona scenarios alone must cover these
        assert {"scheduling", "questions", "edge"} <= categories
        if identity_present:
            assert {"refills", "rescheduling"} <= categories

    def test_minimum_scenario_count(self):
        assert len(list_scenarios()) >= 10
