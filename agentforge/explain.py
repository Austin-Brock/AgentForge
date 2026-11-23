"""Tell the story of one training task in plain language, from the saved event log."""
import textwrap

from agentforge.reflector import SCOPES, summarize_edit
from tasks import FAMILY_LABELS

SCOPE_PLAIN = {
    "execution_slip": "a one-off slip (the agent knew what to do and fumbled it)",
    "agent_behavior": "a bad working habit (something that would matter on any task)",
    "procedure": "a missing or wrong procedure (not knowing how one tool really behaves)",
    "missing_capability": "a missing capability (nobody on the team suited to the work)",
    "routing": "bad planning (the work was split up or handed out badly)",
}
GUARD_PLAIN = {
    "scope_action": "that kind of edit is not allowed for that kind of failure",
    "change_of_strategy": "the same part of the notebook had already been changed twice without success",
    "no_leakage": "the lesson copied this task instead of stating a general rule",
    "prompt_preservation": "it would have thrown away too much of an agent's existing instructions",
    "bounded_growth": "it broke a size or bookkeeping limit",
}
ACTION_PLAIN = {
    "create_skill": "Add a new skill", "revise_skill": "Rewrite an existing skill",
    "refine_prompt": "Change an agent's instructions", "create_agent": "Add a new specialist",
    "memory_note": "Add a planning note", "revise_plan": "Give a hint for the next attempt only",
}


def _wrap(text, indent="    "):
    return textwrap.fill(" ".join(str(text).split()), 96, initial_indent=indent, subsequent_indent=indent)


def explain(task, events, arm):
    mine = [e for e in events if e.get("task") == task.id]
    if not mine:
        return f"Task {task.id} does not appear in this training run."
    lines = [f"TASK {task.id}   (training version: {arm})",
             f"  The unwritten rule behind it: {FAMILY_LABELS[task.family]}", "  The job:", _wrap(task.prompt), ""]
    for e in mine:
        if e["type"] == "attempt":
            how = f"{e['ran_steps']} step(s)"
            if e["skills"]:
                how += f", with skill(s) {', '.join(e['skills'])}"
            if e["notes"]:
                how += f", guided by note(s) {', '.join(e['notes'])}"
            if e["directive"]:
                how += ", following the reviewer's hint"
            lines.append(f"ATTEMPT {e['attempt']}: {'PASSED' if e['passed'] else 'FAILED'}  ({how})")
            lines.append(_wrap("The grader said: " + e["digest"]))
            if not e["ran_code"]:
                lines.append("    The agent submitted without running any code.")
            lines.append("")
        elif e["type"] == "reflection":
            lines.append(f"REVIEW after attempt {e['attempt']}  (the reviewer ran {e['probes']} experiment(s))")
            if e["scope"]:
                lines.append(_wrap(f"Kind of failure: {SCOPE_PLAIN.get(e['scope'], e['scope'])}."))
                lines.append(_wrap(f"Where that kind of lesson belongs: {SCOPES[e['scope']]['level']}."
                                   if e["scope"] in SCOPES else ""))
            lines.append(_wrap("Diagnosis: " + e["diagnosis"]))
            for x in e["refusals"]:
                lines.append(_wrap(f"REFUSED: {ACTION_PLAIN.get(x['action'], x['action'])}, because "
                                   f"{GUARD_PLAIN.get(x['guard'], x['guard'])}."))
                lines.append(_wrap(f'The guard told the reviewer: "{x["reason"]}"', "      "))
            if not e["edits"]:
                lines.append("    Result: nothing was changed in the notebook.")
            for x in e["edits"]:
                lines.append(_wrap(f"{'ACCEPTED' if e['scope'] else 'APPLIED (no checks)'}: "
                                   f"{ACTION_PLAIN.get(x['action'], x['action'])}."))
                lines.append(_wrap(summarize_edit(x["action"], x["payload"])[:700], "      "))
            lines.append("")
        elif e["type"] == "task_end":
            for note in e["notes_added"]:
                lines.append(_wrap(f"PLANNING NOTE ADDED: {note['topic']}: {note['text']}", "  "))
            for x in e["notes_refused"]:
                lines.append(_wrap(f"PLANNING NOTE REFUSED because {GUARD_PLAIN.get(x['guard'], x['guard'])}.", "  "))
            c = e["counts"]
            lines.append(f"OUTCOME: {'solved' if e['passed'] else 'not solved'} in {e['executions']} attempt(s). "
                         f"The notebook now holds {c['skills']} skill(s), {c['notes']} note(s) and "
                         f"{c['agents']} specialist(s).")
            if not e["passed"]:
                lines.append(_wrap("Any lessons accepted along the way stay in the notebook even though the task "
                                   "was not solved. The paper names this as a weakness.", "  "))
    return "\n".join(line for line in lines if line is not None)
