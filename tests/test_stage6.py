"""Stage 6 checks: the held-out evaluation and its summary. No model calls."""
import json

from agentforge.evaluate import evaluate, summarize_arm
from agentforge.llm import ScriptedLLM
from agentforge.memory import Memory, Skill
from tasks import load_tasks

BY_ID = {t.id: t for t in load_tasks()}
PLAN = ScriptedLLM.text(json.dumps({"steps": [{"instruction": "Write it.", "agent": "generalist", "skills": ["s"]}]}))


def test_evaluate_runs_every_arm_on_every_task_and_repeat(tmp_path):
    tasks = [BY_ID["slot2"], BY_ID["slot3"]]
    script = lambda good: ScriptedLLM([r for rep in range(2) for t in tasks
                                       for r in (PLAN, ScriptedLLM.call("submit", code=t.ref if good else t.naive))])
    memories = {"seed": Memory(), "emma": Memory(skills=[Skill("s", "w", "b")])}
    results = evaluate({"seed": script(False), "emma": script(True)}, memories, tasks, 2, tmp_path, workers=1)
    assert [len(v) for v in results.values()] == [4, 4]
    assert not any(r["passed"] for r in results["seed"]) and all(r["passed"] for r in results["emma"])
    assert results["emma"][0]["skills"] == ["s"] and results["seed"][0]["skills"] == []
    assert (tmp_path / "emma.jsonl").read_text().count("\n") == 4


def test_a_crashing_attempt_is_counted_as_a_failure(tmp_path):
    results = evaluate({"seed": ScriptedLLM([])}, {"seed": Memory()}, [BY_ID["slot2"]], 1, tmp_path, workers=1)
    assert results["seed"][0]["error"] == "run" and results["seed"][0]["passed"] is False


def test_summary_reports_rate_spread_and_families():
    rows = [{"task": t, "family": f, "repeat": rep, "passed": p, "skills": [], "ran_code": True, "rounds": 2}
            for rep, outcomes in enumerate([(True, True), (True, False)])
            for (t, f), p in zip([("a", "slots"), ("b", "rates")], outcomes)]
    s = summarize_arm(rows)
    assert (s["passed"], s["attempts"], s["rate"]) == (3, 4, 0.75)
    assert (s["low"], s["high"]) == (0.5, 1.0)
    assert s["families"] == {"slots": {"passed": 2, "attempts": 2}, "rates": {"passed": 1, "attempts": 2}}
    assert (s["tasks_always"], s["tasks_never"]) == (1, 0)
