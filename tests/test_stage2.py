"""Stage 2 checks: the three-level memory and the controller-plus-agents rollout. No model calls."""
import json

from agentforge.gate import gate
from agentforge.llm import ScriptedLLM
from agentforge.memory import GENERALIST_PROMPT, Agent, Memory, Note, Skill
from agentforge.rollout import rollout
from tasks import load_tasks

BY_ID = {t.id: t for t in load_tasks()}
SKILL = Skill("kiln-shelf-slots", "Any step using kiln.Shelf slots", "Slots are numbered from 1.")


def plan_reply(*steps):
    return ScriptedLLM.text(json.dumps({"steps": list(steps)}))


def step(instruction="Write the solution.", agent="generalist", skills=()):
    return {"instruction": instruction, "agent": agent, "skills": list(skills)}


def test_memory_round_trips_and_specialists_inherit_the_generalist(tmp_path):
    memory = Memory(notes=[Note("routing", "Do shelf work in one step.")],
                    agents=[Agent("shelf_worker", "shelf tasks", "Check slot numbers.")], skills=[SKILL])
    memory.save(tmp_path / "m.json")
    loaded = Memory.load(tmp_path / "m.json")
    assert loaded == memory
    assert loaded.prompt_for("shelf_worker") == GENERALIST_PROMPT + "\n\nCheck slot numbers."
    assert loaded.prompt_for("generalist") == GENERALIST_PROMPT


def test_example_memories_load():
    assert Memory.load("examples/fact.json").skills[0].name == "kiln-shelf-slots"
    assert "Before you submit" in Memory.load("examples/habit.json").generalist_prompt


def test_controller_sees_only_the_skill_index_and_the_agent_gets_the_full_text():
    task = BY_ID["slot1"]
    llm = ScriptedLLM([plan_reply(step(skills=["kiln-shelf-slots"])), ScriptedLLM.call("submit", code=task.ref)])
    out = rollout(llm, Memory(skills=[SKILL]), task)
    controller_view = llm.requests[0]["messages"][1]["content"]
    agent_view = llm.requests[1]["messages"][1]["content"]
    assert SKILL.when in controller_view and SKILL.body not in controller_view
    assert SKILL.body in agent_view
    assert out.steps[0]["skills"] == ["kiln-shelf-slots"]
    assert gate(task, out.solution).passed


def test_notes_are_selected_before_planning():
    task = BY_ID["slot1"]
    memory = Memory(notes=[Note("shelves", "One step."), Note("ledgers", "Check dates.")])
    llm = ScriptedLLM([ScriptedLLM.text('{"notes": [0]}'), plan_reply(step()),
                       ScriptedLLM.call("submit", code=task.ref)])
    out = rollout(llm, memory, task)
    assert out.notes == ["shelves"]
    plan_view = llm.requests[1]["messages"][1]["content"]
    assert "One step." in plan_view and "Check dates." not in plan_view


def test_unknown_agents_and_skills_in_a_plan_are_dropped():
    task = BY_ID["slot1"]
    llm = ScriptedLLM([plan_reply(step(agent="nobody", skills=["no-such-skill"])),
                       ScriptedLLM.call("submit", code=task.ref)])
    out = rollout(llm, Memory(), task)
    assert out.steps[0]["agent"] == "generalist" and out.steps[0]["skills"] == []


def test_two_step_plan_passes_findings_forward():
    task = BY_ID["slot1"]
    llm = ScriptedLLM([plan_reply(step("Find how slots are numbered."), step("Write the module.")),
                       ScriptedLLM.call("submit", code="FINDING: slots start at 1"),
                       ScriptedLLM.call("submit", code=task.ref)])
    out = rollout(llm, Memory(), task)
    assert "FINDING: slots start at 1" in llm.requests[2]["messages"][1]["content"]
    assert out.solution == task.ref


def test_overflow_makes_the_controller_split_the_step(monkeypatch):
    monkeypatch.setattr("agentforge.rollout.ROUNDS", 1)
    monkeypatch.setattr("agentforge.rollout.run_agent.__defaults__", (1, "", True))
    task = BY_ID["slot1"]
    llm = ScriptedLLM([plan_reply(step()),
                       ScriptedLLM.call("run_python", code="print(1)"),   # uses the only round: overflow
                       plan_reply(step("Probe the shelf."), step("Write the module.")),
                       ScriptedLLM.call("submit", code="notes"),
                       ScriptedLLM.call("submit", code=task.ref)])
    out = rollout(llm, Memory(), task)
    assert out.overflows == [0]
    assert [s["instruction"] for s in out.steps] == ["Write the solution.", "Probe the shelf.", "Write the module."]
    assert out.solution == task.ref
