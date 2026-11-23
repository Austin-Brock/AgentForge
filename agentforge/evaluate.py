"""The experiment: run each frozen memory on the held-out tasks and compare pass rates.

Nothing learns here. There is no reflector and no writing to memory. Each arm attempts every
held-out task several times, because single runs vary a lot (see stage 2).
"""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean

from agentforge.gate import gate
from agentforge.llm import BudgetExceeded
from agentforge.memory import Memory
from agentforge.rollout import rollout

ARMS = {  # name -> saved memory (None is the empty notebook)
    "seed": None,
    "emma": "runs/train-emma/memory.json",
    "emma-v2": "runs/train-emma-v2/memory.json",
    "unguarded": "runs/train-unguarded/memory.json",
}
ARM_LABELS = {
    "seed": "No notebook",
    "emma": "Careful (EMMA)",
    "emma-v2": "Careful, revised reviewer",
    "unguarded": "Anything-goes",
}


def load_arms(names):
    return {n: Memory.load(ARMS[n]) if ARMS[n] else Memory() for n in names}


def evaluate(llms, memories, tasks, repeats, out_dir, workers=8, log=print):
    """`llms` and `memories` map arm name -> LLM / Memory. Returns {arm: [row, ...]}."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def one(job):
        arm, task, rep = job
        row = {"arm": arm, "task": task.id, "family": task.family, "repeat": rep}
        try:
            trace = rollout(llms[arm], memories[arm], task, salt=f"eval|{rep}")
            result = gate(task, trace.solution)
            row.update(passed=result.passed, digest=result.digest, rounds=trace.rounds,
                       overflows=len(trace.overflows), planned_steps=len(trace.plan), notes=trace.notes,
                       skills=sorted({x for s in trace.steps for x in s["skills"]}),
                       ran_code=any(s["runs"] for s in trace.steps))
        except BudgetExceeded as e:
            row.update(passed=False, digest=str(e), error="budget")
        except Exception as e:  # count as a failure and keep going
            row.update(passed=False, digest=f"{type(e).__name__}: {e}"[:200], error="run")
        return row

    jobs = [(arm, task, rep) for rep in range(repeats) for arm in memories for task in tasks]
    with ThreadPoolExecutor(workers) as pool:
        rows = list(pool.map(one, jobs))
    by_arm = {arm: [r for r in rows if r["arm"] == arm] for arm in memories}
    for arm, arm_rows in by_arm.items():
        (out_dir / f"{arm}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in arm_rows))
    return by_arm


def summarize_arm(rows):
    """Pass rates for one arm: overall, per repeat (to show spread), and per family."""
    repeats = sorted({r["repeat"] for r in rows})
    per_repeat = [mean(r["passed"] for r in rows if r["repeat"] == rep) for rep in repeats]
    families = {}
    for fam in dict.fromkeys(r["family"] for r in rows):
        fam_rows = [r for r in rows if r["family"] == fam]
        families[fam] = {"passed": sum(r["passed"] for r in fam_rows), "attempts": len(fam_rows)}
    tasks = {}
    for r in rows:
        tasks.setdefault(r["task"], []).append(bool(r["passed"]))
    ok = [r for r in rows if not r.get("error")]
    return {
        "attempts": len(rows),
        "passed": sum(r["passed"] for r in rows),
        "rate": mean(r["passed"] for r in rows),
        "per_repeat": per_repeat,
        "low": min(per_repeat),
        "high": max(per_repeat),
        "families": families,
        "tasks_always": sum(all(v) for v in tasks.values()),
        "tasks_never": sum(not any(v) for v in tasks.values()),
        "tasks": len(tasks),
        "errors": len(rows) - len(ok),
        "skill_rate": mean(bool(r["skills"]) for r in ok) if ok else 0,
        "ran_code_rate": mean(r["ran_code"] for r in ok) if ok else 0,
        "avg_rounds": mean(r["rounds"] for r in ok) if ok else 0,
    }


def load_usage(out_dir="runs/eval"):
    """Token usage per arm, merged from every eval run's usage file."""
    usage = {}
    for path in sorted(Path(out_dir).glob("usage*.json")):
        usage.update(json.loads(path.read_text()))
    return usage


def load_results(out_dir="runs/eval"):
    out = {}
    for arm in ARMS:
        path = Path(out_dir) / f"{arm}.jsonl"
        if path.exists():
            out[arm] = [json.loads(line) for line in path.read_text().splitlines()]
    return out
