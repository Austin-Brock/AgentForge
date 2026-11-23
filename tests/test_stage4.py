"""Stage 4 checks: each guard, edit application, and the refuse-and-rewrite loop. No model calls."""
import json

from agentforge import guards
from agentforge.guards import first_violation, reflect_guarded
from agentforge.llm import ScriptedLLM
from agentforge.memory import GENERALIST_PROMPT, Agent, Memory, Skill
from agentforge.reflector import Reflection
from agentforge.rollout import Rollout
from tasks import load_tasks

TASK = {t.id: t for t in load_tasks()}["slot1"]  # first_item(shelf): "Return the item in the first slot of `shelf`."
STEP = {"instruction": "Write it.", "agent": "generalist", "skills": [], "rounds": 1, "overflow": False,
        "runs": [], "result": TASK.naive}
TRACE = Rollout(solution=TASK.naive, plan=[STEP], steps=[STEP])
GOOD_SKILL = {"name": "shelf-slots", "when": "shelf work", "body": "Slots are numbered from 1, not 0."}


def proposal(scope, action, **payload):
    return Reflection(scope=scope, action=action, payload=payload, well_formed=True)


def refused_by(r, memory=None, trace=TRACE, history=()):
    broken = first_violation(r, memory or Memory(), TASK, trace, history)
    return broken[0] if broken else None


def test_a_sound_proposal_is_admissible():
    assert refused_by(proposal("procedure", "create_skill", **GOOD_SKILL)) is None
    assert refused_by(proposal("execution_slip", "no_change")) is None


def test_scope_action_guard():
    assert refused_by(proposal("agent_behavior", "create_skill", **GOOD_SKILL)) == "scope_action"
    assert refused_by(proposal("vibes", "create_skill", **GOOD_SKILL)) == "scope_action"
    assert refused_by(proposal("procedure", "create_skill", name="x", when="", body="b")) == "scope_action"
    agent = dict(name="shelf_worker", description="shelves", prompt="Check slot numbering carefully. " * 6)
    assert refused_by(proposal("routing", "create_agent", **agent)) == "scope_action"  # nothing overflowed
    overflowed = Rollout(plan=[STEP], steps=[{**STEP, "overflow": True}], overflows=[0])
    assert refused_by(proposal("routing", "create_agent", **agent), trace=overflowed) is None


def test_change_of_strategy_guard():
    twice = [{"action": "create_skill"}, {"action": "revise_skill"}]
    assert refused_by(proposal("procedure", "create_skill", **GOOD_SKILL), history=twice) == "change_of_strategy"
    assert refused_by(proposal("procedure", "create_skill", **GOOD_SKILL), history=twice[:1]) is None
    note = dict(topic="planning", text="Use one step for small tasks.", generality="general")
    assert refused_by(proposal("routing", "memory_note", **note), history=twice) is None


def test_no_leakage_guard():
    names_function = dict(GOOD_SKILL, body="def first_item(shelf): return shelf.get(1)")
    assert refused_by(proposal("procedure", "create_skill", **names_function)) == "no_leakage"
    copies_task = dict(GOOD_SKILL, body="To return the item in the first slot of shelf use slot 1.")
    assert refused_by(proposal("procedure", "create_skill", **copies_task)) == "no_leakage"


def test_prompt_preservation_guard():
    replace = proposal("agent_behavior", "refine_prompt", agent="generalist", prompt="Always test your code first.")
    extend = proposal("agent_behavior", "refine_prompt", agent="generalist",
                      prompt=GENERALIST_PROMPT + "\n\nTest your code on a small example before you submit.")
    assert refused_by(replace) == "prompt_preservation"
    assert refused_by(extend) is None
    memory = Memory(agents=[Agent("shelf_worker", "shelves", "Check slot numbers.")])
    idle = proposal("agent_behavior", "refine_prompt", agent="shelf_worker", prompt="Check slot numbers. Twice.")
    assert refused_by(idle, memory) == "prompt_preservation"  # that agent did not run
    assert refused_by(proposal("agent_behavior", "refine_prompt", agent="nobody", prompt="x")) == "prompt_preservation"


def test_bounded_growth_guard():
    has_skill = Memory(skills=[Skill(**GOOD_SKILL)])
    assert refused_by(proposal("procedure", "create_skill", **GOOD_SKILL), has_skill) == "bounded_growth"
    assert refused_by(proposal("procedure", "revise_skill", **GOOD_SKILL)) == "bounded_growth"  # nothing to revise
    assert refused_by(proposal("procedure", "revise_skill", **GOOD_SKILL), has_skill) is None
    long = dict(GOOD_SKILL, body="Slots start at 1. " * 100)
    assert refused_by(proposal("procedure", "create_skill", **long)) == "bounded_growth"
    full = Memory(skills=[Skill(f"s{i}", "w", "b") for i in range(guards.MAX_SKILLS)])
    assert refused_by(proposal("procedure", "create_skill", **GOOD_SKILL), full) == "bounded_growth"
    thin = dict(name="helper", description="helps", prompt="Be careful.")
    assert refused_by(proposal("missing_capability", "create_agent", **thin)) == "bounded_growth"
    clone = dict(name="helper", description="helps", prompt=GENERALIST_PROMPT)
    assert refused_by(proposal("missing_capability", "create_agent", **clone)) == "bounded_growth"


def test_apply_makes_the_edit_and_leaves_the_original_alone():
    memory = Memory()
    after, directive = memory.apply("create_skill", GOOD_SKILL)
    assert after.skill("shelf-slots").body == GOOD_SKILL["body"] and memory.skills == [] and directive == ""
    revised, _ = after.apply("revise_skill", dict(GOOD_SKILL, body="New body."))
    assert revised.skill("shelf-slots").body == "New body."
    noted, _ = memory.apply("memory_note", dict(topic="t", text="x", generality="general"))
    assert noted.notes[0].topic == "t"
    prompted, _ = memory.apply("refine_prompt", dict(agent="generalist", prompt="P"))
    assert prompted.generalist_prompt == "P"
    same, directive = memory.apply("revise_plan", {"directive": "Use one step."})
    assert same == memory and directive == "Use one step."
    assert after.size() > memory.size()


def _answer(scope, action, payload):
    return ScriptedLLM.text(json.dumps({"failing_step": 1, "diagnosis": "d", "scope": scope,
                                        "action": action, "payload": payload}))


PROBE = ScriptedLLM.call("run_python", code="print(1)")
DONE = ScriptedLLM.text("done")


def test_a_refused_proposal_goes_back_with_the_reason_and_the_rewrite_is_accepted():
    llm = ScriptedLLM([PROBE, DONE, _answer("procedure", "revise_skill", GOOD_SKILL),
                       _answer("procedure", "create_skill", GOOD_SKILL)])
    r, refusals = reflect_guarded(llm, Memory(), TASK, "digest", TRACE)
    assert r.action == "create_skill" and [x["guard"] for x in refusals] == ["bounded_growth"]
    retry_view = llm.requests[-1]["messages"][1]["content"]
    assert "Use create_skill" in retry_view and "WHAT YOUR EXPERIMENTS SHOWED" in retry_view
    assert len(llm.requests) == 4  # the retry reused the first round's experiments


def test_three_refusals_end_in_no_change():
    bad = _answer("procedure", "revise_skill", GOOD_SKILL)
    llm = ScriptedLLM([PROBE, DONE, bad, bad, bad])
    r, refusals = reflect_guarded(llm, Memory(), TASK, "digest", TRACE)
    assert r.action == "no_change" and r.scope == "procedure" and len(refusals) == 3
