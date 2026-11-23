"""The reflector: read one failed attempt, assign it to one scope, propose one edit.

This is the paper's Table 1 and the Reflect call of Algorithm 3. Stage 3 has no guards yet:
proposals are recorded, not applied.
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

MAX_PROBES = 3  # sandbox runs the reflector may use to check a hypothesis

PROBE = [tool("run_python", "Run a Python script in a sandbox where `import kiln` works, to check a hypothesis "
                            "about why the attempt failed.", code="The script to run.")]


def _instructions():
    scopes = "\n".join(f"- {name}: {s['meaning']}. Allowed actions: {', '.join(s['actions'])}."
                       for name, s in SCOPES.items())
    payloads = "\n".join(f"- {name}: {shape}" for name, shape in PAYLOADS.items())
    return (
        "A training task FAILED its correctness gate. Diagnose the failure and propose exactly ONE correction "
        "to the team's memory.\n\n"
        "Work in four moves:\n"
        "1. Localize: find the step where things first went wrong.\n"
        "2. Classify: choose the ONE scope that owns the correction.\n"
        "3. Generalize: write the correction so it helps on other tasks of the same kind. Do not mention this "
        "task's function name, its inputs, or any expected value.\n"
        "4. Minimize: propose the smallest edit that would have prevented the failure.\n\n"
        f"Scopes:\n{scopes}\n(create_agent under routing is only for a step that ran out of rounds.)\n\n"
        f"Payload for each action:\n{payloads}\n"
        "create_skill adds a new skill. revise_skill is only for a name already listed under SKILL POOL.\n"
        "A skill body states, in a few sentences, how kiln behaves and what to do about it, with at most a "
        "two-line example. It is never a solution to this task.\n\n"
        "Do not guess. You cannot see the hidden tests; the gate only names the tests that failed. You have "
        f"{MAX_PROBES} rounds of run_python, in a sandbox where the submitted module is importable as "
        "`solution`. First reproduce the failure: call the submitted function on a small case suggested by a "
        "failed test's name and print what it returns. Then probe kiln directly until you can say exactly what "
        "kiln does that the agent did not expect. A diagnosis that says 'likely' or 'possibly' is not finished.\n\n"
        'Final answer, as JSON: {"failing_step": <1-based step number>, "diagnosis": "<one or two sentences>", '
        '"scope": "<scope>", "action": "<action>", "payload": {...}}'
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


def reflect(llm, memory, task, digest, trace, history=(), feedback=(), salt=""):
    """One Reflect call. `feedback` carries guard refusals from earlier rounds (stage 4)."""
    user = describe_attempt(memory, task, digest, trace, list(history))
    if feedback:
        user += "\n\nYOUR EARLIER PROPOSALS WERE REFUSED\n" + "\n".join(f"- {f}" for f in feedback)
    messages = [{"role": "system", "content": _instructions()}, {"role": "user", "content": user}]
    out = Reflection()
    with Workdir() as wd:
        wd.write("solution.py", trace.solution or "")
        for probe_round in range(MAX_PROBES):
            # The first round must be a probe, so a diagnosis is never a pure guess.
            reply = llm.chat(messages, tools=PROBE, force_tool="run_python" if probe_round == 0 else None, salt=salt)
            messages.append(reply.message)
            if not reply.tool_calls:
                break
            for call in reply.tool_calls:
                code = call.args.get("code", "")
                output = wd.run(code)
                out.probes.append({"code": code, "output": output})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
    messages.append({"role": "user", "content": "Give your final answer now, as JSON only."})
    reply = llm.chat(messages, tools=PROBE, force_tool="none", json_mode=True, salt=salt)
    try:
        data = json.loads(reply.content)
    except json.JSONDecodeError:
        data = {}
    if isinstance(data, dict):
        out.scope = str(data.get("scope", ""))
        out.action = str(data.get("action", "no_change"))
        out.payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        out.diagnosis = str(data.get("diagnosis", ""))
        step = data.get("failing_step")
        out.failing_step = step if isinstance(step, int) else 0
    out.well_formed = out.scope in SCOPES and out.action in PAYLOADS
    return out


def summarize(reflection):
    """One line describing the proposed edit."""
    p, a = reflection.payload, reflection.action
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
