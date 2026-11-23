"""Stage 5 checks: the training loop end to end with a scripted model, the unguarded arm, and explain."""
import json

from agentforge.explain import explain
from agentforge.llm import ScriptedLLM
from agentforge.memory import Memory, Skill
from agentforge.train import apply_free, summarize_training, train, training_order
from tasks import load_tasks

BY_ID = {t.id: t for t in load_tasks()}
TASK = BY_ID["slot1"]
SKILL = {"name": "shelf-slots", "when": "any shelf work", "body": "Slots are numbered from 1, not 0."}


def text(obj):
    return ScriptedLLM.text(json.dumps(obj))


def plan(skills=()):
    return text({"steps": [{"instruction": "Write the module.", "agent": "generalist", "skills": list(skills)}]})


def verdict(action, payload):
    return text({"failing_step": 1, "diagnosis": "Used slot 0.", "scope": "procedure",
                 "action": action, "payload": payload})


PROBE, DONE = ScriptedLLM.call("run_python", code="print(1)"), ScriptedLLM.text("done")


def test_training_order_interleaves_families():
    order = [t.id for t in training_order(load_tasks("train"))]
    assert order[:6] == ["mu1", "win1", "slot1", "bp1", "mg1", "sku1"] and len(order) == 18


def test_emma_loop_fail_reflect_refuse_accept_pass(tmp_path):
    llm = ScriptedLLM([
        plan(), ScriptedLLM.call("submit", code=TASK.naive),             # attempt 1 fails
        PROBE, DONE, verdict("revise_skill", SKILL),                     # refused: nothing to revise
        verdict("create_skill", SKILL),                                  # accepted
        plan(["shelf-slots"]), ScriptedLLM.call("submit", code=TASK.ref),  # attempt 2 passes with the skill
        text({"notes": [{"topic": "small tasks", "text": "Use one step.", "generality": "general"}]}),
    ])
    memory, events = train("emma", llm, llm, [TASK], tmp_path, log=lambda *_: None)
    assert [e["type"] for e in events] == ["attempt", "reflection", "attempt", "task_end"]
    assert [e["passed"] for e in events if e["type"] == "attempt"] == [False, True]
    assert events[1]["refusals"][0]["guard"] == "bounded_growth"
    assert events[2]["skills"] == ["shelf-slots"]
    assert memory.skill("shelf-slots") and memory.notes[0].topic == "small tasks"
    assert Memory.load(tmp_path / "memory.json") == memory
    assert (tmp_path / "snapshots" / "01-slot1.json").exists()
    s = summarize_training(events)
    assert (s["after_revision"], s["executions"], s["edits"], s["refusals_by_guard"]) == (1, 2, 1, {"bounded_growth": 1})

    story = explain(TASK, events, "emma")
    assert "ATTEMPT 1: FAILED" in story and "ATTEMPT 2: PASSED" in story
    assert "REFUSED: Rewrite an existing skill" in story and "ACCEPTED: Add a new skill" in story
    assert "PLANNING NOTE ADDED" in story and "solved in 2 attempt(s)" in story


def test_no_edit_is_made_after_the_final_failure(tmp_path):
    fail = [plan(), ScriptedLLM.call("submit", code=TASK.naive)]
    review = [PROBE, DONE, text({"failing_step": 1, "diagnosis": "d", "scope": "execution_slip",
                                 "action": "no_change", "payload": {}})]
    llm = ScriptedLLM(fail + review + fail + [text({"notes": []})])
    memory, events = train("emma", llm, llm, [TASK], tmp_path, k=1, log=lambda *_: None)
    assert [e["type"] for e in events] == ["attempt", "reflection", "attempt", "task_end"]
    assert not events[-1]["passed"] and memory == Memory()


def test_guarded_notes_are_capped_and_checked(tmp_path):
    notes = [{"topic": "a", "text": "Use one step.", "generality": "general"},
             {"topic": "b", "text": "Call first_item directly.", "generality": "general"},  # names the task
             {"topic": "c", "text": "Attach skills.", "generality": "general"},
             {"topic": "d", "text": "A third note.", "generality": "general"}]
    llm = ScriptedLLM([plan(), ScriptedLLM.call("submit", code=TASK.ref), text({"notes": notes})])
    memory, events = train("emma", llm, llm, [TASK], tmp_path, log=lambda *_: None)
    assert [n.topic for n in memory.notes] == ["a", "c"]
    assert events[-1]["notes_refused"][0]["guard"] == "no_leakage"


def test_unguarded_arm_applies_everything_it_is_given(tmp_path):
    edits = [{"action": "revise_skill", "payload": SKILL},                       # missing: becomes a create
             {"action": "refine_prompt", "payload": {"agent": "generalist", "prompt": "Just be right."}},
             {"action": "create_skill", "payload": {"name": "leaky", "when": "w", "body": "def first_item(): ..."}},
             {"action": "nonsense", "payload": {}}]
    llm = ScriptedLLM([
        plan(), ScriptedLLM.call("submit", code=TASK.naive),
        PROBE, DONE, text({"diagnosis": "Used slot 0.", "edits": edits}),
        plan(["shelf-slots"]), ScriptedLLM.call("submit", code=TASK.ref),
        text({"notes": [{"topic": f"n{i}", "text": "x"} for i in range(4)]}),
    ])
    memory, events = train("unguarded", llm, llm, [TASK], tmp_path, log=lambda *_: None)
    assert [s.name for s in memory.skills] == ["shelf-slots", "leaky"]   # the leak got in
    assert memory.generalist_prompt == "Just be right."                  # the prompt was erased
    assert len(memory.notes) == 4                                        # no cap of two
    assert len(events[1]["edits"]) == 3 and events[1]["refusals"] == []
    assert "APPLIED (no checks)" in explain(TASK, events, "unguarded")


def test_apply_free_skips_only_what_cannot_be_done():
    memory = Memory(skills=[Skill("a", "w", "b")])
    out, directive, applied = apply_free(memory, [
        {"action": "create_skill", "payload": {"name": "a", "when": "w2", "body": "b2"}},  # exists: overwritten
        {"action": "refine_prompt", "payload": {"agent": "ghost", "prompt": "x"}},          # no such agent
        {"action": "create_skill", "payload": {"name": "incomplete"}},                      # missing fields
        {"action": "revise_plan", "payload": {"directive": "One step."}},
    ])
    assert out.skill("a").body == "b2" and directive == "One step."
    assert [e["action"] for e in applied] == ["revise_skill", "revise_plan"]
