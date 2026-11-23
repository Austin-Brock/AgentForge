"""The training loop (paper Algorithm 1).

One pass over the training tasks in a fixed order. For each task: try it, grade it, and on
failure reflect, apply the edit, and try again, up to K revisions. Edits accumulate, so later
tasks start with what earlier ones taught. No edit is made after the final failure, because
an edit that is never re-run is untested memory.

Two arms share this loop:
  emma       one scoped edit per failure, checked by the guards
  unguarded  any number of edits anywhere, applied as proposed
"""
import json
from pathlib import Path

from agentforge.gate import gate
from agentforge.guards import first_violation, reflect_guarded
from agentforge.llm import BudgetExceeded
from agentforge.memory import Memory
from agentforge.reflector import PAYLOADS, Reflection, propose_notes, reflect_free, summarize, summarize_edit
from agentforge.rollout import rollout

K_REVISIONS = 3       # revisions per task, so at most K + 1 executions [paper: 5]
NOTES_PER_TASK = 2    # controller notes the end-of-task update may add [paper: 2]


def training_order(tasks):
    """Fixed order that interleaves the families, so no rule is seen three times in a row."""
    return sorted(tasks, key=lambda t: t.position)


def apply_free(memory, edits):
    """Apply the unguarded reflector's edits as proposed. Only edits that cannot be carried out
    at all are skipped. Returns (memory, directive, applied edits)."""
    directive, applied = "", []
    for edit in edits:
        action = edit.get("action")
        payload = {k: str(v) for k, v in edit["payload"].items()}
        try:
            if action == "revise_skill" and not memory.skill(payload["name"]):
                action = "create_skill"
            elif action == "create_skill" and memory.skill(payload["name"]):
                action = "revise_skill"
            if action == "memory_note":
                payload.setdefault("generality", "general")
            if action not in PAYLOADS or action == "no_change":
                continue
            if action == "refine_prompt" and payload["agent"] not in memory.agent_names():
                continue
            if action == "create_agent" and payload["name"] in memory.agent_names():
                continue
            memory, d = memory.apply(action, payload)
        except KeyError:
            continue  # a payload missing a required field
        directive = d or directive
        applied.append({"action": action, "payload": payload})
    return memory, directive, applied


def _controller_update(arm, llm, memory, task, attempts, history, passed, salt):
    """End-of-task notes. In the emma arm each note must pass the guards and at most two are kept."""
    guarded = arm == "emma"
    proposed = propose_notes(llm, memory, task, [(t, r.digest) for t, r in attempts], history, passed,
                             NOTES_PER_TASK if guarded else None, salt=salt)
    added, refused = [], []
    for note in proposed:
        payload = {k: str(note.get(k, "")) for k in ("topic", "text", "generality")}
        if guarded:
            if len(added) >= NOTES_PER_TASK:
                break
            check = Reflection(scope="routing", action="memory_note", payload=payload, well_formed=True)
            broken = first_violation(check, memory, task, attempts[-1][0], [])
            if broken:
                refused.append({"guard": broken[0], "reason": broken[1], "payload": payload})
                continue
        elif not payload["topic"] or not payload["text"]:
            continue
        memory, _ = memory.apply("memory_note", payload)
        added.append(payload)
    return memory, added, refused


def train(arm, exec_llm, ref_llm, tasks, out_dir, k=K_REVISIONS, log=print):
    out_dir = Path(out_dir)
    (out_dir / "snapshots").mkdir(parents=True, exist_ok=True)
    memory = Memory()
    events = []
    log_file = (out_dir / "events.jsonl").open("w")

    def emit(**event):
        events.append(event)
        log_file.write(json.dumps(event) + "\n")
        log_file.flush()

    try:
        for n, task in enumerate(tasks, 1):
            history, directive, attempts, trail = [], "", [], []
            for attempt in range(k + 1):
                trace = rollout(exec_llm, memory, task, salt=f"train|{arm}|{attempt}", directive=directive)
                result = gate(task, trace.solution)
                attempts.append((trace, result))
                trail.append("pass" if result.passed else "fail")
                emit(type="attempt", task=task.id, family=task.family, attempt=attempt + 1, passed=result.passed,
                     digest=result.digest, directive=directive, notes=trace.notes, planned_steps=len(trace.plan),
                     ran_steps=len(trace.steps), overflows=len(trace.overflows),
                     agents=sorted({s["agent"] for s in trace.steps}),
                     skills=sorted({x for s in trace.steps for x in s["skills"]}),
                     ran_code=any(s["runs"] for s in trace.steps), solution=trace.solution)
                if result.passed or attempt == k:
                    break
                salt = f"train|{arm}|{attempt}"
                if arm == "emma":
                    r, refusals = reflect_guarded(ref_llm, memory, task, result.digest, trace, history, salt=salt)
                    memory, directive = memory.apply(r.action, r.payload)
                    edits = [] if r.action == "no_change" else [{"action": r.action, "payload": r.payload}]
                    history.append({"scope": r.scope, "action": r.action, "diagnosis": r.diagnosis})
                    emit(type="reflection", task=task.id, attempt=attempt + 1, scope=r.scope, diagnosis=r.diagnosis,
                         edits=edits, refusals=refusals, probes=len(r.probes), memory_size=memory.size())
                    trail.append(f"[{r.scope}/{r.action}{' after %d refusal(s)' % len(refusals) if refusals else ''}]")
                else:
                    diagnosis, proposed, probes = reflect_free(ref_llm, memory, task, result.digest, trace,
                                                               history, salt=salt)
                    memory, directive, edits = apply_free(memory, proposed)
                    actions = ", ".join(e["action"] for e in edits) or "no_change"
                    history.append({"scope": "any", "action": actions, "diagnosis": diagnosis})
                    emit(type="reflection", task=task.id, attempt=attempt + 1, scope="", diagnosis=diagnosis,
                         edits=edits, refusals=[], probes=len(probes), memory_size=memory.size())
                    trail.append(f"[{len(edits)} edit(s): {actions}]")
            passed = attempts[-1][1].passed
            memory, added, refused = _controller_update(arm, ref_llm, memory, task, attempts, history, passed,
                                                        salt=f"train|{arm}")
            emit(type="task_end", task=task.id, family=task.family, passed=passed, executions=len(attempts),
                 notes_added=added, notes_refused=refused, memory_size=memory.size(),
                 counts={"notes": len(memory.notes), "agents": len(memory.agents), "skills": len(memory.skills)})
            memory.save(out_dir / "snapshots" / f"{n:02d}-{task.id}.json")
            notes = f" +{len(added)} note(s)" if added else ""
            log(f"{n:>2}/{len(tasks)} {task.id:<6} {' -> '.join(trail)}{notes}")
    except BudgetExceeded as e:
        emit(type="stopped", reason=str(e))
        log(f"Stopped early: {e}")
    finally:
        log_file.close()
        memory.save(out_dir / "memory.json")
    return memory, events


def summarize_training(events):
    """Headline numbers for a finished training run."""
    ends = [e for e in events if e["type"] == "task_end"]
    reflections = [e for e in events if e["type"] == "reflection"]
    edits = [x for e in reflections for x in e["edits"]]
    by_action = {}
    for x in edits:
        by_action[x["action"]] = by_action.get(x["action"], 0) + 1
    by_guard = {}
    for e in reflections:
        for x in e["refusals"]:
            by_guard[x["guard"]] = by_guard.get(x["guard"], 0) + 1
    return {
        "tasks": len(ends),
        "first_try": sum(e["passed"] and e["executions"] == 1 for e in ends),
        "after_revision": sum(e["passed"] and e["executions"] > 1 for e in ends),
        "never": sum(not e["passed"] for e in ends),
        "executions": sum(e["executions"] for e in ends),
        "reflections": len(reflections),
        "edits": len(edits),
        "edits_by_action": by_action,
        "no_change": sum(not e["edits"] for e in reflections),
        "refusals_by_guard": by_guard,
        "notes_added": sum(len(e["notes_added"]) for e in ends),
        "notes_refused": sum(len(e["notes_refused"]) for e in ends),
        "final": ends[-1]["counts"] if ends else {},
        "final_size": ends[-1]["memory_size"] if ends else 0,
        "stopped": any(e["type"] == "stopped" for e in events),
    }


__all__ = ["train", "training_order", "apply_free", "summarize_training", "summarize", "summarize_edit"]
