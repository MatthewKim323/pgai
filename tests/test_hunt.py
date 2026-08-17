"""Hunt generation: leads in, validated runnable scenario out."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from caller.hunt import generate_hunt
from caller.scenario import load_scenario

KNOWLEDGE = {
    "practice_facts": [{"text": "Provider name: Dr. Howser", "source": "01"}],
    "leads": [{"text": "transfers appear to reach a dead end", "source": "02"}],
}

SPEC = {
    "title": "Caller with a billing question asks to be transferred",
    "first_name": "Nadia",
    "last_name": "Petrov",
    "dob": "1985-05-20",
    "phone": "6265550142",
    "insurance": "United PPO",
    "background": "Got a confusing bill after a visit.",
    "goal": "Understand the bill; if the agent offers a transfer, accept it.",
    "steering": ["Ask to speak with billing directly."],
    "targeted_leads": ["transfers appear to reach a dead end"],
}


def tool_response(payload):
    return SimpleNamespace(
        stop_reason="tool_use",
        content=[SimpleNamespace(type="tool_use", input=payload)],
    )


class TestGenerateHunt:
    def test_generates_loadable_scenario(self, tmp_path):
        client = MagicMock()
        client.messages.create.return_value = tool_response(SPEC)
        hunt_id = generate_hunt(client, "m", KNOWLEDGE, tmp_path)
        assert hunt_id == "hunt-1"

        s = load_scenario(hunt_id, tmp_path)
        assert s.category == "hunt"
        assert s.persona.full_name == "Nadia Petrov"
        assert s.persona.voice_id.startswith("aura-2")
        assert "transfer" in s.goal

        # leads and facts made it into the generator prompt
        prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "dead end" in prompt and "Dr. Howser" in prompt

    def test_ids_increment(self, tmp_path):
        client = MagicMock()
        client.messages.create.return_value = tool_response(SPEC)
        assert generate_hunt(client, "m", KNOWLEDGE, tmp_path) == "hunt-1"
        assert generate_hunt(client, "m", KNOWLEDGE, tmp_path) == "hunt-2"

    def test_invalid_spec_leaves_no_file(self, tmp_path):
        client = MagicMock()
        client.messages.create.return_value = tool_response({**SPEC, "dob": "not-a-date"})
        from caller.scenario import ScenarioError

        with pytest.raises(ScenarioError):
            generate_hunt(client, "m", KNOWLEDGE, tmp_path)
        assert list(tmp_path.glob("hunt-*.yaml")) == []

    def test_no_leads_refuses(self, tmp_path):
        with pytest.raises(ValueError, match="no leads"):
            generate_hunt(MagicMock(), "m", {"practice_facts": [], "leads": []}, tmp_path)
