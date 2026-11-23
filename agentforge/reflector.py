"""The reflector: read one failed attempt, assign it to one scope, propose one edit.

This is the paper's Table 1 and the Reflect call of Algorithm 3. It also holds the two
variants used in training: the unguarded reflector (any edits, anywhere) and the
end-of-task controller update.
"""
import json
from dataclasses import asdict, dataclass, field

from agentforge.llm import tool
from agentforge.sandbox import Workdir

# Paper Table 1: each scope owns a level of memory and allows only certain actions.
SCOPES = {
    "execution_slip": {
        "meaning": "the agent knew the method and slipped once, for example it submitted the wrong thing",
        "level": "none (this attempt only)",
        "actions": ["revise_plan", "no_change"],
    },
    "agent_behavior": {
        "meaning": "a general working habit failed, one that would matter on any kind of task",
        "level": "agent prompt",
        "actions": ["refine_prompt"],
    },
    "procedure": {
        "meaning": "the method for a class of sub-problems was wrong or missing, for example a fact "
                   "about how a library function behaves",
        "level": "skill pool",
        "actions": ["create_skill", "revise_skill"],
    },
    "missing_capability": {
        "meaning": "no agent in the pool is suited to this kind of work",
        "level": "skill pool, then agent pool",
        "actions": ["create_skill", "create_agent"],
    },
    "routing": {
        "meaning": "the individual steps were sound but the task was split up or handed out badly",
        "level": "controller notes",
        "actions": ["memory_note", "revise_plan", "create_agent"],
    },
}

PAYLOADS = {
    "no_change": "{}",
    "revise_plan": '{"directive": "<one sentence for the controller, for the next attempt at this task only>"}',
    "refine_prompt": '{"agent": "<agent name>", "prompt": "<the full new prompt for that agent>"}',
    "create_skill": '{"name": "<kebab-case>", "when": "<one line: when to attach it>", "body": "<the procedure>"}',
    "revise_skill": '{"name": "<existing skill name>", "when": "<one line>", "body": "<the full new procedure>"}',
    "create_agent": '{"name": "<snake_case>", "description": "<one line: what it is for>", '
                    '"prompt": "<role-specific instructions only>"}',
    "memory_note": '{"topic": "<short>", "text": "<1 to 3 sentences>", "generality": "general|domain_specific"}',
}

MAX_PROBES = 3  # sandbox rounds the reflector may use to check a hypothesis

PROBE = [tool("run_python", "Run a Python script in a sandbox where `import kiln` works, to check a hypothesis "
                            "about why the attempt failed.", code="The script to run.")]

_PAYLOAD_LIST = "\n".join(f"- {name}: {shape}" for name, shape in PAYLOADS.items())

# Both the guarded and the unguarded reflector investigate the same way. They differ only in
# what they are allowed to change.
INVESTIGATE = (
    "Do not guess. You cannot see the hidden tests; the gate only names the tests that failed. You have "
    f"{MAX_PROBES} rounds of run_python, in a sandbox where the submitted module is importable as "
    "`solution`. First reproduce the failure: call the submitted function on a small case suggested by a "
    "failed test's name and print what it returns. Then probe kiln directly until you can say exactly what "
    "kiln does that the agent did not expect. A diagnosis that says 'likely' or 'possibly' is not finished."
)


# The one change in the emma-v2 arm. The original wording produced lessons too vague to use
# (stage 5), so this version asks for the kiln function and its observed behaviour by name.
GENERALIZE_V1 = (
    "3. Generalize: write the correction so it helps on other tasks of the same kind. Do not mention this "
    "task's function name, its inputs, or any expected value.\n"
)
GENERALIZE_V2 = (
    "3. Generalize: write the correction so it helps on other tasks that use the same part of kiln. Name the "
    "kiln function or method involved and state exactly what it does, as your experiments showed it: for "
    "example which end of a range is left out, which value means 'not found', or what unit an argument is in. "
    "General means reusable on other tasks, not vague. Do not mention this task's own function name, its "
    "inputs, or any expected value.\n"
)


def _instructions(specific=False):
    scopes = "\n".join(f"- {name}: {s['meaning']}. Allowed actions: {', '.join(s['actions'])}."
                       for name, s in SCOPES.items())
    return (
        "A training task FAILED its correctness gate. Diagnose the failure and propose exactly ONE correction "
        "to the team's memory.\n\n"
        "Work in four moves:\n"
        "1. Localize: find the step where things first went wrong.\n"
        "2. Classify: choose the ONE scope that owns the correction.\n"
        + (GENERALIZE_V2 if specific else GENERALIZE_V1) +
        "4. Minimize: propose the smallest edit that would have prevented the failure.\n\n"
        f"Scopes:\n{scopes}\n(create_agent under routing is only for a step that ran out of rounds.)\n\n"
        f"Payload for each action:\n{_PAYLOAD_LIST}\n"
        "create_skill adds a new skill. revise_skill is only for a name already listed under SKILL POOL.\n"
        "A skill body states, in a few sentences, how kiln behaves and what to do about it, with at most a "
        "two-line example. It is never a solution to this task.\n\n"
        f"{INVESTIGATE}\n\n"
        'Final answer, as JSON: {"failing_step": <1-based step number>, "diagnosis": "<one or two sentences>", '
        '"scope": "<scope>", "action": "<action>", "payload": {...}}'
    )


FREE_INSTRUCTIONS = (
    "A training task FAILED its correctness gate. Improve the team's memory so that the team does better on "
    "future tasks. You may make any number of edits, of any kind, anywhere in memory.\n\n"
    f"Edits available, with their payloads:\n{_PAYLOAD_LIST}\n\n"
    f"{INVESTIGATE}\n\n"
    'Final answer, as JSON: {"diagnosis": "<one or two sentences>", '
    '"edits": [{"action": "<action>", "payload": {...}}, ...]}'
)


@dataclass
class Reflection:
    scope: str = ""
    action: str = "no_change"
    payload: dict = field(default_factory=dict)
    diagnosis: str = ""
    failing_step: int = 0
    probes: list = field(default_factory=list)
    well_formed: bool = False  # scope and action are known names (not yet a guard check)

    def to_dict(self):
        return asdict(self)


def describe_attempt(memory, task, digest, trace, history):
    """Everything the reflector is shown about one failed attempt."""
    parts = [f"TASK\n{task.render()}", f"GATE RESULT\n{digest}"]
    parts.append("CONTROLLER NOTES LOADED\n" + ("\n".join(f"- {t}" for t in trace.notes) or "(none)"))
    plan = "\n".join(f"{i}. [{s['agent']}; skills: {', '.join(s['skills']) or 'none'}] {s['instruction']}"
                     for i, s in enumerate(trace.plan, 1))
    parts.append(f"PLAN\n{plan}")
    for i, s in enumerate(trace.steps, 1):
        runs = "\n".join(f"  ran:\n{r['code'][:600]}\n  output:\n{r['output'][:600]}" for r in s["runs"][-4:])
        parts.append(
            f"STEP {i} [{s['agent']}; skills: {', '.join(s['skills']) or 'none'}]"
            f"{' RAN OUT OF ROUNDS' if s['overflow'] else ''}\ninstruction: {s['instruction']}\n"
            f"{runs or '  (ran no code)'}\n  submitted:\n{s['result'][:1500]}"
        )
    agents = sorted({s["agent"] for s in trace.steps})
    parts.append("PROMPTS OF THE AGENTS THAT RAN\n" + "\n\n".join(f"[{a}]\n{memory.prompt_for(a)}" for a in agents))
    used = [memory.skill(n) for n in sorted({n for s in trace.steps for n in s["skills"]})]
    parts.append("SKILL POOL (name: when)\n" + memory.skill_index())
    if used:
        parts.append("SKILLS ATTACHED IN THIS ATTEMPT\n" + "\n\n".join(f"## {s.name}\n{s.body}" for s in used if s))
    parts.append(f"AGENT POOL\n{memory.agent_index()}")
    if history:
        past = "\n".join(f"- {h['scope']} -> {h['action']}: {h['diagnosis']} (still failed)" for h in history)
        parts.append(f"EARLIER CORRECTIONS TRIED ON THIS TASK\n{past}")
    return "\n\n".join(parts)


def _investigate_and_answer(llm, system, user, trace, salt, prior_probes=()):
    """Let the model probe the sandbox, then collect its final JSON. Returns (answer dict, probes)."""
    if prior_probes:
        user += "\n\nWHAT YOUR EXPERIMENTS SHOWED\n" + "\n".join(
            f"ran:\n{p['code'][:600]}\noutput:\n{p['output'][:600]}" for p in prior_probes)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    probes = list(prior_probes)
    with Workdir() as wd:
        wd.write("solution.py", trace.solution or "")
        for probe_round in range(0 if prior_probes else MAX_PROBES):
            # The first round must be a probe, so a diagnosis is never a pure guess.
            reply = llm.chat(messages, tools=PROBE, force_tool="run_python" if probe_round == 0 else None, salt=salt)
            messages.append(reply.message)
            if not reply.tool_calls:
                break
            for call in reply.tool_calls:
                code = call.args.get("code", "")
                output = wd.run(code)
                probes.append({"code": code, "output": output})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
    messages.append({"role": "user", "content": "Give your final answer now, as JSON only."})
    reply = llm.chat(messages, tools=PROBE, force_tool="none", json_mode=True, salt=salt)
    try:
        data = json.loads(reply.content)
    except json.JSONDecodeError:
        data = {}
    return (data if isinstance(data, dict) else {}), probes


def reflect(llm, memory, task, digest, trace, history=(), feedback=(), salt="", prior_probes=(), specific=False):
    """One guarded-style Reflect call. `feedback` carries guard refusals from earlier rounds;
    `prior_probes` carries the experiments already run, so a retry does not repeat them."""
    user = describe_attempt(memory, task, digest, trace, list(history))
    if feedback:
        user += "\n\nYOUR EARLIER PROPOSALS WERE REFUSED\n" + "\n".join(f"- {f}" for f in feedback)
    data, probes = _investigate_and_answer(llm, _instructions(specific), user, trace, salt, prior_probes)
    step = data.get("failing_step")
    out = Reflection(
        scope=str(data.get("scope", "")), action=str(data.get("action", "no_change")),
        payload=data.get("payload") if isinstance(data.get("payload"), dict) else {},
        diagnosis=str(data.get("diagnosis", "")), failing_step=step if isinstance(step, int) else 0, probes=probes,
    )
    out.well_formed = out.scope in SCOPES and out.action in PAYLOADS
    return out


def reflect_free(llm, memory, task, digest, trace, history=(), salt=""):
    """The unguarded reflector: same evidence and experiments, but no scopes, no one-edit limit.

    Returns (diagnosis, edits, probes), where edits is a list of {"action", "payload"}.
    """
    user = describe_attempt(memory, task, digest, trace, list(history))
    user += "\n\nCONTROLLER NOTES (all)\n" + ("\n".join(f"- {n.topic}: {n.text}" for n in memory.notes) or "(none)")
    data, probes = _investigate_and_answer(llm, FREE_INSTRUCTIONS, user, trace, salt)
    edits = [e for e in data.get("edits") or [] if isinstance(e, dict) and isinstance(e.get("payload"), dict)]
    return str(data.get("diagnosis", "")), edits, probes


def propose_notes(llm, memory, task, attempts, history, passed, limit, salt=""):
    """End-of-task controller update (paper Algorithm 1, step 11): propose notes about planning.

    `attempts` is a list of (trace, digest). `limit` is how many notes may be proposed, or None.
    """
    lines = []
    for i, (trace, digest) in enumerate(attempts, 1):
        steps = "; ".join(f"[{s['agent']}; skills: {', '.join(s['skills']) or 'none'}] {s['instruction'][:120]}"
                          for s in trace.plan)
        lines.append(f"Attempt {i}: planned {len(trace.plan)} steps, ran {len(trace.steps)}, "
                     f"{len(trace.overflows)} ran out of rounds. {digest}\n  plan: {steps}")
    past = "\n".join(f"- {h['scope']} -> {h['action']}: {h['diagnosis']}" for h in history) or "(none)"
    notes = "\n".join(f"- [{n.generality}] {n.topic}: {n.text}" for n in memory.notes) or "(none)"
    cap = f"Add at most {limit} notes" if limit else "Add any notes you think useful"
    prompt = (
        f"A training task has finished: it {'PASSED' if passed else 'FAILED'} after {len(attempts)} attempt(s).\n"
        "You maintain the controller's notes: short rules about how to split a task into steps, which agent to "
        "give a step to, which skills to attach, and how to check results.\n\n"
        f"TASK\n{task.render()}\n\nATTEMPTS\n" + "\n".join(lines) + f"\n\nCORRECTIONS TRIED\n{past}\n\n"
        f"SKILL POOL (name: when)\n{memory.skill_index()}\n\nAGENT POOL\n{memory.agent_index()}\n\n"
        f"EXISTING NOTES\n{notes}\n\n"
        f"{cap}, and only if this task taught something about planning or routing that the existing notes do "
        "not already say. Most tasks need none. Notes must be general: do not mention this task's function or "
        "copy its wording.\n"
        'Reply as JSON: {"notes": [{"topic": "<short>", "text": "<1 to 3 sentences>", '
        '"generality": "general|domain_specific"}]}'
    )
    reply = llm.chat([{"role": "system", "content": "You maintain a planning notebook. Reply with JSON only."},
                      {"role": "user", "content": prompt}], json_mode=True, salt=salt)
    try:
        data = json.loads(reply.content)
    except json.JSONDecodeError:
        data = {}
    notes = data.get("notes") if isinstance(data, dict) else None
    return [n for n in notes or [] if isinstance(n, dict)]


def summarize_edit(action, payload):
    """One line describing an edit."""
    p, a = payload, action
    if a in ("create_skill", "revise_skill"):
        return f"skill '{p.get('name', '?')}': {p.get('body', '')}"
    if a == "refine_prompt":
        return f"new prompt for {p.get('agent', '?')}: {p.get('prompt', '')}"
    if a == "create_agent":
        return f"agent '{p.get('name', '?')}' ({p.get('description', '')}): {p.get('prompt', '')}"
    if a == "memory_note":
        return f"note '{p.get('topic', '?')}': {p.get('text', '')}"
    if a == "revise_plan":
        return f"directive: {p.get('directive', '')}"
    return "nothing"


def summarize(reflection):
    return summarize_edit(reflection.action, reflection.payload)
