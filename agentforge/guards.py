"""The guards (paper Section 3.2.2): ordinary code that accepts or refuses a proposed edit.

No model is involved, so the limits hold whatever model is doing the proposing. Guards check
an edit's form: where it goes, how big it is, how much it changes, whether it copies the task.
They cannot check whether a lesson is true. Only re-running the task can do that.
"""
import re
from difflib import SequenceMatcher

from agentforge.memory import GENERALIST
from agentforge.reflector import PAYLOADS, SCOPES, Reflection, reflect

# Limits. The paper's values (in brackets) are scaled down for this small task set.
MAX_AGENTS = 6               # including the generalist [10]
MAX_SKILLS = 20              # [40]
MAX_NOTES = 15               # [15 loaded per task]
PROMPT_CHARS = 2000          # per agent prompt [6,000]
SKILL_CHARS = 1200           # per skill [3,000]
NOTE_CHARS = 400
KEEP_FRACTION = 0.6          # share of an existing prompt an edit must keep [0.6]
MIN_SPECIALIZATION = 150     # characters a new agent's own prompt must have [150]
LEAK_WORDS = 8               # longest run of task wording an edit may copy [15; tasks here are one or two sentences]
SAME_LEVEL_LIMIT = 2         # failed revisions in a row allowed on one level [2]
REFUSAL_ROUNDS = 3           # proposals per failure before giving up [3]

# Which level of memory each action edits.
LEVEL = {
    "memory_note": "controller notes", "refine_prompt": "agents", "create_agent": "agents",
    "create_skill": "skills", "revise_skill": "skills", "revise_plan": "the plan", "no_change": None,
}
REQUIRED = {name: re.findall(r'"(\w+)":', shape) for name, shape in PAYLOADS.items()}


def _words(text):
    return re.findall(r"[a-z0-9_]+", text.lower())


def _units(text):
    """A prompt's lines and sentences, the pieces that prompt preservation counts."""
    return [u.strip() for u in re.split(r"(?<=[.!?])\s+|\n+", text) if u.strip()]


def scope_action(r, memory, task, trace, history):
    """The edit must be one that the diagnosed scope allows, and be completely filled in."""
    if r.scope not in SCOPES:
        return f"'{r.scope}' is not a scope. Choose one of: {', '.join(SCOPES)}."
    if r.action not in SCOPES[r.scope]["actions"]:
        return f"Scope {r.scope} does not allow {r.action}. It allows: {', '.join(SCOPES[r.scope]['actions'])}."
    if r.action == "create_agent" and r.scope == "routing" and not trace.overflows:
        return "Under routing, create_agent is only allowed when a step ran out of rounds, and none did."
    missing = [k for k in REQUIRED[r.action] if not str(r.payload.get(k, "")).strip()]
    if missing:
        return f"The {r.action} payload is missing: {', '.join(missing)}."
    return None


def change_of_strategy(r, memory, task, trace, history):
    """After two failed fixes in a row at one level, the next fix must try a different level."""
    level = LEVEL[r.action]
    recent = [LEVEL.get(h["action"]) for h in history[-SAME_LEVEL_LIMIT:]]
    if level and len(recent) == SAME_LEVEL_LIMIT and all(x == level for x in recent):
        return (f"The last {SAME_LEVEL_LIMIT} corrections on this task both edited {level} and it still failed. "
                "Propose a correction at a different level.")
    return None


def no_leakage(r, memory, task, trace, history):
    """A lesson must not carry this task's own function or wording into memory."""
    text = " ".join(str(v) for v in r.payload.values())
    function = task.signature.split("(")[0]
    if re.search(rf"\b{re.escape(function)}\b", text):
        return (f"The edit names this task's own function ({function}). Describe the general situation instead, "
                "so the lesson applies to other tasks.")
    task_words, edit_words = _words(task.prompt), " ".join(_words(text))
    for i in range(len(task_words) - LEAK_WORDS + 1):
        span = " ".join(task_words[i:i + LEAK_WORDS])
        if span in edit_words:
            return f"The edit copies the task's wording (\"{span}...\"). Put the lesson in your own general words."
    return None


def prompt_preservation(r, memory, task, trace, history):
    """A prompt edit must keep most of the existing prompt and only touch an agent that ran."""
    if r.action != "refine_prompt":
        return None
    name = r.payload["agent"]
    if name not in memory.agent_names():
        return f"There is no agent named '{name}'. Agents: {', '.join(memory.agent_names())}."
    if name not in {s["agent"] for s in trace.steps}:
        return f"Agent '{name}' did not run in the failed attempt, so its prompt may not be edited."
    old = memory.generalist_prompt if name == GENERALIST else next(a.prompt for a in memory.agents if a.name == name)
    new_units = set(_units(r.payload["prompt"]))
    old_units = _units(old)
    kept = sum(u in new_units for u in old_units) / len(old_units)
    if kept < KEEP_FRACTION:
        return (f"The new prompt keeps {kept:.0%} of the existing prompt's sentences; at least "
                f"{KEEP_FRACTION:.0%} must be kept word for word. Add to the prompt instead of replacing it.")
    return None


def bounded_growth(r, memory, task, trace, history):
    """Memory has a fixed size: caps on pools and entries, and new agents must be real specialists."""
    p, a = r.payload, r.action
    if a == "create_skill":
        if memory.skill(p["name"]):
            return f"A skill named '{p['name']}' already exists. Use revise_skill to change it."
        if len(memory.skills) >= MAX_SKILLS:
            return f"The skill pool is full ({MAX_SKILLS}). Revise an existing skill instead."
    if a == "revise_skill" and not memory.skill(p["name"]):
        names = ", ".join(s.name for s in memory.skills) or "none yet"
        return f"There is no skill named '{p['name']}' to revise (existing skills: {names}). Use create_skill."
    if a in ("create_skill", "revise_skill") and len(p["body"]) > SKILL_CHARS:
        return f"The skill body is {len(p['body'])} characters; the limit is {SKILL_CHARS}."
    if a == "refine_prompt" and len(p["prompt"]) > PROMPT_CHARS:
        return f"The prompt is {len(p['prompt'])} characters; the limit is {PROMPT_CHARS}."
    if a == "create_agent":
        if p["name"] in memory.agent_names():
            return f"An agent named '{p['name']}' already exists."
        if len(memory.agent_names()) >= MAX_AGENTS:
            return f"The agent pool is full ({MAX_AGENTS})."
        if not MIN_SPECIALIZATION <= len(p["prompt"]) <= PROMPT_CHARS:
            return (f"A new agent's own prompt must be {MIN_SPECIALIZATION} to {PROMPT_CHARS} characters of "
                    f"role-specific instructions; this one is {len(p['prompt'])}.")
        for other in [memory.generalist_prompt] + [x.prompt for x in memory.agents]:
            if SequenceMatcher(None, p["prompt"], other).ratio() > 0.8:
                return "The new agent's prompt nearly repeats an existing agent's. It must be a real specialisation."
    if a == "memory_note":
        if len(memory.notes) >= MAX_NOTES:
            return f"Controller notes are full ({MAX_NOTES})."
        if len(p["text"]) > NOTE_CHARS:
            return f"The note is {len(p['text'])} characters; the limit is {NOTE_CHARS}."
        if p["generality"] not in ("general", "domain_specific"):
            return "A note's generality must be 'general' or 'domain_specific'."
    return None


GUARDS = [scope_action, change_of_strategy, no_leakage, prompt_preservation, bounded_growth]


def first_violation(r, memory, task, trace, history=()):
    """Return (guard name, reason) for the first guard the proposal breaks, or None if it is admissible."""
    if r.action == "no_change" and r.scope in SCOPES:
        return None
    for guard in GUARDS:
        why = guard(r, memory, task, trace, list(history))
        if why:
            return guard.__name__, why
    return None


def reflect_guarded(llm, memory, task, digest, trace, history=(), salt="", specific=False):
    """Paper Algorithm 3: propose, check, and send refusals back, up to REFUSAL_ROUNDS times.

    Returns (reflection, refusals). If every proposal is refused the result is no_change.
    """
    feedback, refusals, probes, r = [], [], (), Reflection()
    for _ in range(REFUSAL_ROUNDS):
        r = reflect(llm, memory, task, digest, trace, history, feedback, salt=salt, prior_probes=probes,
                    specific=specific)
        probes = probes or r.probes
        broken = first_violation(r, memory, task, trace, history)
        if not broken:
            return r, refusals
        guard, why = broken
        refusals.append({"guard": guard, "reason": why, "scope": r.scope, "action": r.action, "payload": r.payload})
        feedback.append(f"{r.action}: {why}")
    given_up = Reflection(scope=r.scope, action="no_change", diagnosis=r.diagnosis,
                          failing_step=r.failing_step, probes=list(probes), well_formed=r.scope in SCOPES)
    return given_up, refusals
