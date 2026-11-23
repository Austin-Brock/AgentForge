"""Stage 3 checks: the reflector's inputs and outputs. No model calls."""
import json

from agentforge.llm import ScriptedLLM
from agentforge.memory import Memory, Skill
from agentforge.reflector import PAYLOADS, SCOPES, describe_attempt, reflect, summarize
from agentforge.rollout import Rollout
from tasks import load_tasks

TASK = {t.id: t for t in load_tasks()}["slot1"]
TRACE = Rollout(
    solution=TASK.naive, plan=[{"instruction": "Write it.", "agent": "generalist", "skills": []}],
    steps=[{"instruction": "Write it.", "agent": "generalist", "skills": [], "rounds": 1, "overflow": False,
            "runs": [{"code": "print(1)", "output": "1"}], "result": TASK.naive}],
)
DIGEST = "2 of 2 tests failed: test_three_items (wrong result); test_one_item (wrong result)"


def answer(**fields):
    return ScriptedLLM.text(json.dumps(fields))


def test_every_scope_action_has_a_payload_shape():
    assert len(SCOPES) == 5
    assert all(a in PAYLOADS for s in SCOPES.values() for a in s["actions"])


def test_reflector_sees_the_attempt_but_never_the_hidden_tests():
    memory = Memory(skills=[Skill("other-skill", "when dates", "body text")])
    shown = describe_attempt(memory, TASK, DIGEST, TRACE, [])
    assert DIGEST in shown and "shelf.get(0)" in shown and "other-skill: when dates" in shown
    assert TASK.tests not in shown and "_shelf(" not in shown and TASK.ref not in shown


def test_reflect_can_probe_the_sandbox_then_returns_one_proposal():
    proposal = {"name": "shelf-slots", "when": "shelf work", "body": "Slots start at 1."}
    llm = ScriptedLLM([
        ScriptedLLM.call("run_python", code="import kiln; s = kiln.Shelf(1); s.put(1, 'a'); print(s.get(0), s.get(1))"),
        ScriptedLLM.text("I have what I need."),
        answer(failing_step=1, diagnosis="Used slot 0.", scope="procedure", action="create_skill", payload=proposal),
    ])
    r = reflect(llm, Memory(), TASK, DIGEST, TRACE)
    assert r.probes[0]["output"].strip() == "None a"
    assert (r.scope, r.action, r.payload, r.failing_step, r.well_formed) == ("procedure", "create_skill", proposal, 1, True)
    assert llm.requests[0]["force_tool"] == "run_python" and llm.requests[-1]["force_tool"] == "none"
    assert "Slots start at 1." in summarize(r)


def test_garbage_or_unknown_names_are_marked_not_well_formed():
    assert not reflect(ScriptedLLM([ScriptedLLM.text("x"), ScriptedLLM.text("not json")]),
                       Memory(), TASK, DIGEST, TRACE).well_formed
    r = reflect(ScriptedLLM([ScriptedLLM.text("x"), answer(scope="vibes", action="rewrite_everything", payload={})]),
                Memory(), TASK, DIGEST, TRACE)
    assert not r.well_formed


def test_history_and_refusals_are_passed_back_to_the_reflector():
    llm = ScriptedLLM([ScriptedLLM.text("x"), answer(scope="execution_slip", action="no_change", payload={})])
    reflect(llm, Memory(), TASK, DIGEST, TRACE,
            history=[{"scope": "procedure", "action": "create_skill", "diagnosis": "first idea"}],
            feedback=["That proposal copied text from the task."])
    shown = llm.requests[0]["messages"][1]["content"]
    assert "first idea (still failed)" in shown and "copied text from the task" in shown
