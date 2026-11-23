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


def cmd_run(args):
    """Run the agent team on the tasks with a fixed memory and report how often it passes."""
    need_key()
    from agentforge.llm import LLM
    from agentforge.memory import Memory
    from agentforge.rollout import rollout

    llm = LLM(model=args.model, max_tokens_total=args.max_tokens_total)
    memory = Memory.load(args.memory) if args.memory else Memory()
    label = args.label or (Path(args.memory).stem if args.memory else "seed")
    tasks = [t for t in load_tasks() if not args.family or t.family == args.family]
    tasks = tasks[: args.limit] if args.limit else tasks

    def one(task):
        try:
            run = rollout(llm, memory, task, salt=args.salt)
            result = gate(task, run.solution)
            return {"task": task.id, "family": task.family, "split": task.split, "passed": result.passed,
                    "digest": result.digest, "rounds": run.rounds, "overflows": len(run.overflows),
                    "ran_code": any(s["runs"] for s in run.steps),
                    "skills_used": sorted({n for s in run.steps for n in s["skills"]}),
                    "notes": run.notes, "plan": run.plan, "steps": run.steps, "solution": run.solution}
        except Exception as e:  # keep the other tasks going; report this one as an error
            return {"task": task.id, "family": task.family, "split": task.split, "passed": False,
                    "digest": f"run error: {type(e).__name__}: {e}", "error": True}

    print(f"Running '{label}' memory ({llm.model}) on {len(tasks)} tasks: {len(memory.notes)} notes, "
          f"{len(memory.agents)} specialists, {len(memory.skills)} skills...")
    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(one, tasks))

    out = Path("runs") / label
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
    ok = [r for r in rows if not r.get("error")]
    print(f"Ran code before submitting on {sum(r['ran_code'] for r in ok)} of {len(ok)} tasks; "
          f"attached a skill on {sum(bool(r['skills_used']) for r in ok)}.")
    errors = [r for r in rows if r.get("error")]
    if errors:
        print(f"\n{len(errors)} tasks hit a run error (counted as failed). First: {errors[0]['digest']}")
    if args.failures:
        print("\nFailures:")
        for r in rows:
            if not r["passed"]:
                print(f"  {r['task']:<6} {r['digest']}")
    u = llm.usage
    print(f"\nTokens: {u['input']:,} in, {u['output']:,} out over {u['calls']} calls "
          f"({u['cached_calls']} more served from cache). Details: {out / 'results.jsonl'}")


def cmd_reflect(args):
    """Show the reflector's diagnosis of every failure in a saved run. Nothing is applied."""
    need_key()
    from agentforge.guards import reflect_guarded
    from agentforge.llm import LLM, reflector_model
    from agentforge.memory import Memory
    from agentforge.reflector import SCOPES, reflect, summarize
    from agentforge.rollout import Rollout

    folder = Path("runs") / args.run
    if not (folder / "results.jsonl").exists():
        sys.exit(f"No saved run at {folder}. Run `python -m agentforge run` first.")
    rows = [json.loads(line) for line in (folder / "results.jsonl").read_text().splitlines()]
    failed = [r for r in rows if not r["passed"] and not r.get("error")
              and (args.split == "all" or r["split"] == args.split)]
    failed = failed[: args.limit] if args.limit else failed
    tasks = {t.id: t for t in load_tasks()}
    memory = Memory.load(args.memory) if args.memory else Memory()
    llm = LLM(model=args.model or reflector_model(), max_tokens_total=args.max_tokens_total)

    def one(row):
        trace = Rollout(solution=row["solution"], notes=row.get("notes", []), plan=row["plan"], steps=row["steps"],
                        overflows=[i for i, s in enumerate(row["steps"]) if s["overflow"]])
        try:
            if args.guards:
                r, refusals = reflect_guarded(llm, memory, tasks[row["task"]], row["digest"], trace)
            else:
                r, refusals = reflect(llm, memory, tasks[row["task"]], row["digest"], trace), []
        except Exception as e:
            return {"task": row["task"], "family": row["family"], "error": f"{type(e).__name__}: {e}"}
        return {"task": row["task"], "family": row["family"], "summary": summarize(r),
                "refusals": refusals, **r.to_dict()}

    print(f"Reflecting on {len(failed)} failed tasks from the '{args.run}' run ({llm.model})...")
    with ThreadPoolExecutor(args.workers) as pool:
        out = list(pool.map(one, failed))
    good = [r for r in out if "error" not in r]
    saved = folder / f"reflections-{'guarded-' if args.guards else ''}{llm.model}.jsonl"
    saved.write_text("".join(json.dumps(r) + "\n" for r in out))
    for r in good if not args.quiet else []:
        print(f"\n{r['task']} ({r['family']})  ->  {r['scope'] or '?'} / {r['action']}"
              f"{'' if r['well_formed'] else '   [not a valid scope or action]'}")
        print(f"  diagnosis: {r['diagnosis']}")
        for x in r["refusals"]:
            print(f"  REFUSED {x['action']} by {x['guard']}: {x['reason']}")
        print(f"  {'accepted' if args.guards else 'proposed'} {r['summary'][:args.width]}")

    print(f"\n{'family':<13}" + "".join(f"{s[:13]:>15}" for s in SCOPES) + f"{'other':>8}")
    for fam in FAMILY_LABELS:
        rs = [r for r in good if r["family"] == fam]
        if rs:
            counts = [sum(r["scope"] == s for r in rs) for s in SCOPES]
            print(f"{fam:<13}" + "".join(f"{c:>15}" for c in counts) + f"{len(rs) - sum(counts):>8}")

    # Signs of what would go wrong if every proposal were accepted as it stands.
    def text(r):
        return json.dumps(r["payload"])
    leaks = [r["task"] for r in good if tasks[r["task"]].signature.split("(")[0] in text(r)]
    new_skills = [r for r in good if r["action"] == "create_skill"]
    names = {r["payload"].get("name") for r in new_skills}
    mismatched = [r["task"] for r in good if r["well_formed"] and r["action"] not in SCOPES[r["scope"]]["actions"]]
    longest = max((len(text(r)) for r in good), default=0)
    actions = sorted({r["action"] for r in good})
    print("\nActions proposed: " + ", ".join(f"{sum(r['action'] == a for r in good)} {a}" for a in actions))
    ghosts = [r["task"] for r in good if r["action"] == "revise_skill" and not memory.skill(r["payload"].get("name"))]
    print(f"{len(ghosts)} proposals revise a skill that does not exist.")
    if args.guards:
        from collections import Counter

        refused = Counter(x["guard"] for r in good for x in r["refusals"])
        print(f"Guards: {sum(not r['refusals'] for r in good)} of {len(good)} accepted first time; "
              f"{sum(bool(r['refusals']) and r['action'] != 'no_change' for r in good)} accepted after a rewrite; "
              f"{sum(bool(r['refusals']) and r['action'] == 'no_change' for r in good)} given up as no change.")
        print("Refusals by guard: " + (", ".join(f"{n} {g}" for g, n in refused.most_common()) or "none"))
    print(f"If every {'accepted ' if args.guards else ''}proposal were {'applied' if args.guards else 'accepted'}: {len(new_skills)} new skills under {len(names)} different names; "
          f"{len(leaks)} proposals name the task's own function; {len(mismatched)} use an action their scope "
          f"does not allow; {sum(not r['well_formed'] for r in good)} are malformed; the longest is {longest:,} characters.")
    errors = [r for r in out if "error" in r]
    if errors:
        print(f"{len(errors)} reflections hit an error. First: {errors[0]['error']}")
    u = llm.usage
    print(f"Tokens: {u['input']:,} in, {u['output']:,} out over {u['calls']} calls. "
          f"Details: {saved}")


def cmd_train(args):
    """Run the learning loop over the training tasks and save the memory it produces."""
    need_key()
    from agentforge.llm import LLM, reflector_model
    from agentforge.train import summarize_training, train, training_order

    exec_llm = LLM(model=args.model, max_tokens_total=args.max_exec_tokens)
    ref_llm = LLM(model=reflector_model(), max_tokens_total=args.max_reflector_tokens)
    tasks = training_order(load_tasks("train"))
    tasks = tasks[: args.limit] if args.limit else tasks
    out = Path("runs") / f"train-{args.arm}"
    print(f"Training the '{args.arm}' version on {len(tasks)} tasks, up to {args.k} revisions each "
          f"(workers: {exec_llm.model}, reviewer: {ref_llm.model})...")
    memory, events = train(args.arm, exec_llm, ref_llm, tasks, out, k=args.k)
    s = summarize_training(events)
    print(f"\nTasks: {s['first_try']} passed first try, {s['after_revision']} passed after a revision, "
          f"{s['never']} never passed ({s['executions']} executions in all).")
    actions = ", ".join(f"{n} {a}" for a, n in sorted(s["edits_by_action"].items())) or "none"
    print(f"Reviews: {s['reflections']}, producing {s['edits']} edits ({actions}); "
          f"{s['no_change']} reviews changed nothing.")
    if args.arm.startswith("emma"):
        guards = ", ".join(f"{n} {g}" for g, n in sorted(s["refusals_by_guard"].items())) or "none"
        print(f"Guard refusals: {guards}. Planning notes: {s['notes_added']} added, {s['notes_refused']} refused.")
    else:
        print(f"Planning notes added at task end: {s['notes_added']}.")
    print(f"Final memory: {len(memory.skills)} skills, {len(memory.notes)} notes, {len(memory.agents)} specialists, "
          f"{memory.size():,} characters. Saved to {out / 'memory.json'}")
    for name, llm in (("Workers", exec_llm), ("Reviewer", ref_llm)):
        u = llm.usage
        print(f"{name} tokens: {u['input']:,} in, {u['output']:,} out over {u['calls']} calls "
              f"({u['cached_calls']} from cache).")


def cmd_explain(args):
    """Tell the story of one training task in plain language."""
    from agentforge.explain import explain

    path = Path("runs") / f"train-{args.arm}" / "events.jsonl"
    if not path.exists():
        sys.exit(f"No training run at {path.parent}. Run `python -m agentforge train --arm {args.arm}` first.")
    task = next((t for t in load_tasks() if t.id == args.task), None)
    if task is None:
        sys.exit(f"No task named {args.task}.")
    print(explain(task, [json.loads(line) for line in path.read_text().splitlines()], args.arm))


def print_eval(results, usage=None):
    from agentforge.evaluate import ARM_LABELS, summarize_arm

    summaries = {arm: summarize_arm(rows) for arm, rows in results.items() if rows}
    print(f"\n{'version':<28}{'pass rate':>10}{'range over repeats':>21}{'passes':>10}")
    for arm, s in summaries.items():
        spread = f"{100 * s['low']:.0f}% to {100 * s['high']:.0f}%"
        print(f"{ARM_LABELS[arm]:<28}{100 * s['rate']:>9.0f}%{spread:>21}{s['passed']:>6}/{s['attempts']}")
    print(f"\n{'passes by rule':<28}" + "".join(f"{f[:11]:>12}" for f in FAMILY_LABELS))
    for arm, s in summaries.items():
        cells = [f"{s['families'][f]['passed']}/{s['families'][f]['attempts']}" if f in s["families"] else "-"
                 for f in FAMILY_LABELS]
        print(f"{ARM_LABELS[arm]:<28}" + "".join(f"{c:>12}" for c in cells))
    print(f"\n{'how each worked':<28}{'used a skill':>13}{'tested code':>13}{'avg rounds':>12}{'errors':>8}"
          + ("  tokens" if usage else ""))
    for arm, s in summaries.items():
        tokens = f"  {usage[arm]['input'] + usage[arm]['output']:,}" if usage and arm in usage else ""
        print(f"{ARM_LABELS[arm]:<28}{100 * s['skill_rate']:>12.0f}%{100 * s['ran_code_rate']:>12.0f}%"
              f"{s['avg_rounds']:>12.1f}{s['errors']:>8}{tokens}")


def cmd_eval(args):
    """Run each frozen notebook on the held-out tasks, several times, and compare pass rates."""
    from agentforge.evaluate import ARMS, evaluate, load_arms, load_results, load_usage

    out = Path("runs/eval")
    if not args.show:
        need_key()
        from agentforge.llm import LLM

        arms = args.arms or [a for a in ARMS if ARMS[a] is None or Path(ARMS[a]).exists()]
        missing = [a for a in arms if ARMS[a] and not Path(ARMS[a]).exists()]
        if missing:
            sys.exit(f"No trained notebook for: {', '.join(missing)}. Train those versions first.")
        llms = {a: LLM(model=args.model, max_tokens_total=args.max_tokens_per_arm) for a in arms}
        tasks = load_tasks("heldout")
        print(f"Evaluating {', '.join(arms)} on {len(tasks)} held-out tasks, {args.repeats} times each "
              f"({len(arms) * len(tasks) * args.repeats} attempts, {next(iter(llms.values())).model})...")
        evaluate(llms, load_arms(arms), tasks, args.repeats, out, workers=args.workers)
        # One usage file per eval run, so runs started at different times cannot overwrite each other.
        (out / f"usage-{'-'.join(arms)}.json").write_text(json.dumps({a: llm.usage for a, llm in llms.items()}))
    results = load_results(out)
    if not results:
        sys.exit("No evaluation results yet. Run `python -m agentforge eval` first.")
    print_eval(results, load_usage(out))


def cmd_report(args):
    """Build the results page from the saved training and evaluation runs."""
    from agentforge.report import build

    print(f"Wrote {build(args.out)}. Open it in a browser.")


def main(argv=None):
    load_env()
    parser = argparse.ArgumentParser(prog="agentforge")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check-tasks", help="verify the task set without calling a model").set_defaults(fn=cmd_check_tasks)
    sub.add_parser("models", help="list the model IDs your OpenAI key can use").set_defaults(fn=cmd_models)

    p = sub.add_parser("show", help="print one task as the agent sees it")
    p.add_argument("task")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("run", aliases=["calibrate"],
                       help="run the agent team with a fixed memory (default: empty) and report its pass rate")
    p.add_argument("--memory", help="a memory JSON file, for example examples/fact.json")
    p.add_argument("--label", help="name for the output folder under runs/")
    p.add_argument("--failures", action="store_true", help="list every failed task")
    p.add_argument("--model")
    p.add_argument("--family", choices=list(FAMILY_LABELS))
    p.add_argument("--limit", type=int)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--salt", default="", help="change to get a fresh sample instead of cached replies")
    p.add_argument("--max-tokens-total", type=int, default=2_000_000)
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("reflect", help="diagnose every failure in a saved run (nothing is applied)")
    p.add_argument("--run", default="seed", help="folder under runs/ (default: seed)")
    p.add_argument("--memory", help="the memory file that run used, if any")
    p.add_argument("--split", choices=["train", "heldout", "all"], default="train",
                   help="which failures to reflect on (default: train, so held-out tasks stay unseen)")
    p.add_argument("--limit", type=int)
    p.add_argument("--width", type=int, default=260, help="characters of each proposal to print")
    p.add_argument("--quiet", action="store_true", help="print only the summary")
    p.add_argument("--guards", action="store_true", help="check each proposal with the guards and let the "
                   "reflector rewrite refused ones")
    p.add_argument("--model", help="reflector model (default: AGENTFORGE_REFLECTOR_MODEL)")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--max-tokens-total", type=int, default=2_000_000)
    p.set_defaults(fn=cmd_reflect)

    p = sub.add_parser("train", help="run the learning loop and save the memory it produces")
    p.add_argument("--arm", choices=["emma", "emma-v2", "unguarded"], default="emma",
                   help="emma: one scoped, guarded edit per failure. unguarded: any edits, no checks")
    p.add_argument("--k", type=int, default=3, help="revisions allowed per task")
    p.add_argument("--limit", type=int, help="train on only the first N tasks")
    p.add_argument("--model", help="worker model (default: AGENTFORGE_MODEL)")
    p.add_argument("--max-exec-tokens", type=int, default=3_000_000)
    p.add_argument("--max-reflector-tokens", type=int, default=1_200_000)
    p.set_defaults(fn=cmd_train)

    p = sub.add_parser("explain", help="tell the story of one training task in plain language")
    p.add_argument("task")
    p.add_argument("--arm", choices=["emma", "emma-v2", "unguarded"], default="emma")
    p.set_defaults(fn=cmd_explain)

    p = sub.add_parser("eval", help="compare the frozen notebooks on the held-out tasks")
    p.add_argument("--arms", nargs="+", choices=["seed", "emma", "emma-v2", "unguarded"],
                   help="versions to evaluate (default: every version that has been trained)")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--show", action="store_true", help="print the saved results without running anything")
    p.add_argument("--model", help="worker model (default: AGENTFORGE_MODEL)")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--max-tokens-per-arm", type=int, default=1_500_000)
    p.set_defaults(fn=cmd_eval)

    p = sub.add_parser("report", help="build the results page from the saved runs")
    p.add_argument("--out", default="docs/index.html")
    p.set_defaults(fn=cmd_report)

    args = parser.parse_args(argv)
    sys.exit(args.fn(args) or 0)


if __name__ == "__main__":
    main()
