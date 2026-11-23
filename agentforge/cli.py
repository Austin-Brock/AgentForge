"""Command line: python -m agentforge <command>."""
import argparse
import json
import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agentforge.gate import gate
from tasks import FAMILY_LABELS, load_tasks


def load_env(path=".env"):
    """Read KEY=VALUE lines from .env without overriding the real environment."""
    if not Path(path).exists():
        return
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            # Names are upper-cased so `Openai_api_key=` works as well as `OPENAI_API_KEY=`.
            os.environ.setdefault(key.strip().upper(), value.strip().strip("\"'"))


def need_key():
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set. Copy .env.example to .env and add your key.")


def cmd_check_tasks(args):
    """Every reference solution must pass its hidden tests and every naive one must fail."""
    bad = 0
    for t in load_tasks():
        ref, naive = gate(t, t.ref), gate(t, t.naive)
        if not ref.passed or naive.passed:
            bad += 1
            print(f"PROBLEM {t.id}: reference passed={ref.passed} ({ref.digest}); naive passed={naive.passed}")
    tasks = load_tasks()
    print(f"{len(tasks) - bad} of {len(tasks)} tasks are sound "
          f"({len(load_tasks('train'))} train, {len(load_tasks('heldout'))} held out).")
    return 1 if bad else 0


def cmd_models(args):
    need_key()
    from openai import OpenAI

    for model in sorted(m.id for m in OpenAI().models.list()):
        print(model)


def cmd_show(args):
    """Print what the agent is given for one task."""
    task = next((t for t in load_tasks() if t.id == args.task), None)
    if task is None:
        sys.exit(f"No task named {args.task}.")
    print(task.render())


def cmd_calibrate(args):
    """Run the untrained agent on the tasks and report how often it passes."""
    need_key()
    from agentforge.llm import LLM
    from agentforge.rollout import rollout_seed

    llm = LLM(model=args.model, max_tokens_total=args.max_tokens_total)
    tasks = [t for t in load_tasks() if not args.family or t.family == args.family]
    tasks = tasks[: args.limit] if args.limit else tasks

    def one(task):
        try:
            run = rollout_seed(llm, task, salt=args.salt)
            result = gate(task, run.solution)
            return {"task": task.id, "family": task.family, "split": task.split, "passed": result.passed,
                    "digest": result.digest, "rounds": run.rounds, "overflow": run.overflow,
                    "steps": run.steps, "solution": run.solution}
        except Exception as e:  # keep the other tasks going; report this one as an error
            return {"task": task.id, "family": task.family, "split": task.split, "passed": False,
                    "digest": f"run error: {type(e).__name__}: {e}", "error": True}

    print(f"Running the untrained agent ({llm.model}) on {len(tasks)} tasks...")
    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(one, tasks))

    out = Path("runs/calibrate")
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    by_family = defaultdict(list)
    for r in rows:
        by_family[r["family"]].append(r)
    print(f"\n{'family':<13}{'passed':>8}   convention")
    for fam, rs in by_family.items():
        print(f"{fam:<13}{sum(r['passed'] for r in rs):>4}/{len(rs):<3}   {FAMILY_LABELS[fam]}")
    passed = sum(r["passed"] for r in rows)
    print(f"{'ALL':<13}{passed:>4}/{len(rows):<3}   {100 * passed / len(rows):.0f}% pass rate")
    errors = [r for r in rows if r.get("error")]
    if errors:
        print(f"\n{len(errors)} tasks hit a run error (counted as failed). First: {errors[0]['digest']}")
    print("\nFailures:")
    for r in rows:
        if not r["passed"]:
            print(f"  {r['task']:<6} {r['digest']}")
    u = llm.usage
    print(f"\nTokens: {u['input']:,} in, {u['output']:,} out over {u['calls']} calls "
          f"({u['cached_calls']} more served from cache). Details: {out / 'results.jsonl'}")


def main(argv=None):
    load_env()
    parser = argparse.ArgumentParser(prog="agentforge")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check-tasks", help="verify the task set without calling a model").set_defaults(fn=cmd_check_tasks)
    sub.add_parser("models", help="list the model IDs your OpenAI key can use").set_defaults(fn=cmd_models)

    p = sub.add_parser("show", help="print one task as the agent sees it")
    p.add_argument("task")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("calibrate", help="run the untrained agent and report its pass rate")
    p.add_argument("--model")
    p.add_argument("--family", choices=list(FAMILY_LABELS))
    p.add_argument("--limit", type=int)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--salt", default="", help="change to get a fresh sample instead of cached replies")
    p.add_argument("--max-tokens-total", type=int, default=2_000_000)
    p.set_defaults(fn=cmd_calibrate)

    args = parser.parse_args(argv)
    sys.exit(args.fn(args) or 0)


if __name__ == "__main__":
    main()
