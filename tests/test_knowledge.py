"""Cross-call knowledge: extraction, dedup, and persona-safe rendering."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from caller import knowledge, store
from caller.scenario import build_system_prompt, load_scenario
from caller.turnstate import TurnStateMachine


def tool_response(payload):
    return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=payload)])


def seed_call(tmp_path, scenario="refill"):
    call_dir = store.create_call_dir(scenario, tmp_path)
    m = TurnStateMachine()
    m.on_call_connected(0.0)
    m.on_agent_vad_start(1.0)
    m.on_agent_transcript("We have a ten thirty slot with doctor Abricker.", 2.0)
    m.on_agent_vad_stop(2.2)
    m.on_call_ended(3.0)
    store.save_artifacts(call_dir, m, 0.0, meta={"scenario": scenario, "call_sid": "CA1"})
    return call_dir


class TestUpdateFromCall:
    def test_accumulates_and_dedups(self, tmp_path):
        call_dir = seed_call(tmp_path)
        client = MagicMock()
        client.messages.create.return_value = tool_response(
            {"practice_facts": ["Dr. Abricker sees patients."], "leads": ["accept a transfer"]}
        )
        k = knowledge.update_from_call(client, "m", call_dir, tmp_path)
        assert k["practice_facts"][0]["text"] == "Dr. Abricker sees patients."
        assert k["practice_facts"][0]["source"] == call_dir.name

        # same facts again: nothing duplicated
        second = seed_call(tmp_path)
        k = knowledge.update_from_call(client, "m", second, tmp_path)
        assert len(k["practice_facts"]) == 1
        assert len(k["leads"]) == 1

    def test_known_facts_passed_to_extractor(self, tmp_path):
        call_dir = seed_call(tmp_path)
        client = MagicMock()
        client.messages.create.return_value = tool_response(
            {"practice_facts": ["fact one"], "leads": []}
        )
        knowledge.update_from_call(client, "m", call_dir, tmp_path)
        knowledge.update_from_call(client, "m", seed_call(tmp_path), tmp_path)
        prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "fact one" in prompt  # extractor sees the known list

    def test_persisted_to_disk(self, tmp_path):
        call_dir = seed_call(tmp_path)
        client = MagicMock()
        client.messages.create.return_value = tool_response(
            {"practice_facts": ["f"], "leads": []}
        )
        knowledge.update_from_call(client, "m", call_dir, tmp_path)
        on_disk = json.loads((tmp_path / "knowledge.json").read_text())
        assert on_disk["practice_facts"][0]["text"] == "f"


class TestPromptBlock:
    def test_empty_knowledge_renders_nothing(self):
        assert knowledge.prompt_block({"practice_facts": [], "leads": []}) == ""

    def test_hearsay_framing(self):
        block = knowledge.prompt_block(
            {
                "practice_facts": [{"text": "Dr. Abricker works there.", "source": "01"}],
                "leads": [{"text": "accept a transfer offer", "source": "02"}],
            }
        )
        assert "a friend of yours" in block
        assert "Dr. Abricker works there." in block
        assert "accept a transfer offer" in block
        assert "never explain why" in block

    def test_caps_item_count(self):
        facts = [{"text": f"fact {i}", "source": "x"} for i in range(20)]
        block = knowledge.prompt_block({"practice_facts": facts, "leads": []}, max_items=3)
        assert "fact 19" in block and "fact 0" not in block

    def test_flows_into_system_prompt(self, tmp_path):
        (tmp_path / "s.yaml").write_text(
            "id: s\ntitle: t\ncategory: c\n"
            "persona: {first_name: A, last_name: B}\ngoal: do the thing\n"
        )
        s = load_scenario("s", tmp_path)
        block = knowledge.prompt_block(
            {"practice_facts": [{"text": "Open until five.", "source": "01"}], "leads": []}
        )
        prompt = build_system_prompt(s, knowledge_block=block)
        assert "Open until five." in prompt
        # and without it, nothing leaks
        assert "friend of yours" not in build_system_prompt(s)
