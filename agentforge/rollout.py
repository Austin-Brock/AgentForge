"""Running the agent team on one task (a simplified version of the paper's Algorithm 2).

A controller reads its notes, plans steps, and gives each step to an agent along with any
skills that apply. Each agent works in a tool loop: run code in the sandbox, then submit.
An agent that runs out of rounds has "overflowed": the controller splits the step and resumes.
"""
import json
from dataclasses import dataclass, field

from agentforge.llm import tool
from agentforge.memory import GENERALIST, Memory
from agentforge.sandbox import Workdir

TOOLS = [
    tool("run_python", "Run a Python script in the sandbox and return its output.",
         code="The script to run."),
    tool("submit", "Hand in the result of your step. Ends the step.",
         code="For the final step, the full source of the solution module. Otherwise, your findings."),
]

ROUNDS = 8       # tool-loop rounds per step (R in the paper)
MAX_PLAN = 4     # plan steps (K_pi)
MAX_SPLITS = 2   # overflow decompositions per task
MAX_EXECUTED = 8 # hard stop on steps actually run

CONTROLLER_PROMPT = (
    "You are the controller of a small team of coding agents. You never write the solution "
    "yourself. You break a task into steps, give each step to one agent, and attach any skills "
    "that apply. Reply with JSON only."
)


@dataclass
class AgentRun:
    solution: str = ""
    steps: list = field(default_factory=list)  # [{"code": ..., "output": ...}]
    rounds: int = 0
    overflow: bool = False  # ran out of rounds before submitting


@dataclass
class Rollout:
    solution: str = ""
    notes: list = field(default_factory=list)      # topics of the controller notes loaded
    plan: list = field(default_factory=list)       # the plan as first written
    steps: list = field(default_factory=list)      # what actually ran
    overflows: list = field(default_factory=list)  # indexes into steps

    @property
    def rounds(self):
        return sum(s["rounds"] for s in self.steps)


def run_agent(llm, system_prompt, task_text, rounds=ROUNDS, salt="", force_on_overflow=True):
    run = AgentRun()
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": task_text}]
    with Workdir() as wd:
        for run.rounds in range(1, rounds + 1):
            reply = llm.chat(messages, tools=TOOLS, salt=salt)
            messages.append(reply.message)
            if not reply.tool_calls:
                messages.append({"role": "user", "content": "Call run_python to test code, or submit to finish."})
                continue
            for call in reply.tool_calls:
                code = call.args.get("code", "")
                if call.name == "submit":
                    run.solution = code
                    return run
                output = wd.run(code)
                run.steps.append({"code": code, "output": output})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
        run.overflow = True
        if force_on_overflow:
            messages.append({"role": "user", "content": "You are out of rounds. Submit your best result now."})
            reply = llm.chat(messages, tools=TOOLS, force_tool="submit", salt=salt)
            for call in reply.tool_calls:
                if call.name == "submit":
                    run.solution = call.args.get("code", "")
    return run


def _ask_json(llm, prompt, salt):
    reply = llm.chat([{"role": "system", "content": CONTROLLER_PROMPT}, {"role": "user", "content": prompt}],
                     json_mode=True, salt=salt)
    try:
        data = json.loads(reply.content)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _clean_steps(raw, memory, limit):
    """Keep well-formed steps; unknown agents fall back to the generalist, unknown skills are dropped."""
    steps = []
    for s in raw if isinstance(raw, list) else []:
        if isinstance(s, dict) and str(s.get("instruction", "")).strip():
            agent = s.get("agent") if s.get("agent") in memory.agent_names() else GENERALIST
            skills = [n for n in s.get("skills") or [] if memory.skill(n)]
            steps.append({"instruction": str(s["instruction"]), "agent": agent, "skills": skills})
    return steps[:limit]


def select_notes(llm, memory, task_text, salt):
    """The controller reads the index of its notes and loads the ones it wants. None is allowed."""
    if not memory.notes:
        return []
    index = "\n".join(f"{i}. [{n.generality}] {n.topic}" for i, n in enumerate(memory.notes))
    data = _ask_json(llm, f"{task_text}\n\nYour notes, by number:\n{index}\n\n"
                          'Which notes apply to this task? Reply as JSON: {"notes": [<numbers>]}', salt)
    picked = [i for i in data.get("notes") or [] if isinstance(i, int) and 0 <= i < len(memory.notes)]
    return [memory.notes[i] for i in dict.fromkeys(picked)]


def plan(llm, memory, task_text, notes, directive, salt):
    notes_text = "\n".join(f"- {n.topic}: {n.text}" for n in notes) or "(none)"
    prompt = (
        f"{task_text}\n\nYour notes:\n{notes_text}\n\nAgents:\n{memory.agent_index()}\n\n"
        f"Skills (attach one to a step when its line applies):\n{memory.skill_index()}\n\n"
        + (f"Directive for this attempt: {directive}\n\n" if directive else "")
        + f"Plan at most {MAX_PLAN} steps. Use one step unless the task clearly has separable parts. "
        "The last step must produce the final solution module.\n"
        'Reply as JSON: {"steps": [{"instruction": "...", "agent": "<agent name>", "skills": ["<skill name>"]}]}'
    )
    steps = _clean_steps(_ask_json(llm, prompt, salt).get("steps"), memory, MAX_PLAN)
    return steps or [{"instruction": "Write the solution module.", "agent": GENERALIST, "skills": []}]


def decompose(llm, memory, task_text, step, run, salt):
    """After an overflow, the controller splits the unfinished step into smaller ones."""
    work = "\n".join(f"ran:\n{s['code'][:400]}\noutput:\n{s['output'][:400]}" for s in run.steps[-3:])
    prompt = (
        f"{task_text}\n\nAn agent ran out of rounds on this step without finishing:\n{step['instruction']}\n\n"
        f"Its last attempts:\n{work or '(nothing run)'}\n\nAgents:\n{memory.agent_index()}\n\n"
        f"Skills:\n{memory.skill_index()}\n\nSplit the step into 2 or 3 smaller steps that together finish it.\n"
        'Reply as JSON: {"steps": [{"instruction": "...", "agent": "<agent name>", "skills": ["<skill name>"]}]}'
    )
    return _clean_steps(_ask_json(llm, prompt, salt).get("steps"), memory, 3)


def _step_text(task_text, step, final, skills, earlier):
    parts = [task_text, f"Your step: {step['instruction']}"]
    parts.append("This is the final step: submit the complete solution module." if final else
                 "This is an intermediate step: submit your findings as text for the next step.")
    if skills:
        parts.append("Skills for this step:\n" + "\n\n".join(f"## {s.name}\n{s.body}" for s in skills))
    if earlier:
        parts.append("Results of earlier steps:\n" + "\n---\n".join(e[:1500] for e in earlier))
    return "\n\n".join(parts)


def rollout(llm, memory, task, salt="", directive=""):
    text = task.render()
    notes = select_notes(llm, memory, text, salt)
    steps = plan(llm, memory, text, notes, directive, salt)
    out = Rollout(notes=[n.topic for n in notes], plan=[dict(s) for s in steps])
    results, splits, i = [], 0, 0
    while i < len(steps) and len(out.steps) < MAX_EXECUTED:
        step, final = steps[i], i == len(steps) - 1
        skills = [memory.skill(n) for n in step["skills"]]
        can_split = splits < MAX_SPLITS
        run = run_agent(llm, memory.prompt_for(step["agent"]), _step_text(text, step, final, skills, results),
                        salt=salt, force_on_overflow=not can_split)
        out.steps.append({**step, "runs": run.steps, "rounds": run.rounds,
                          "overflow": run.overflow, "result": run.solution})
        if run.overflow:
            out.overflows.append(len(out.steps) - 1)
            if can_split:
                splits += 1
                smaller = decompose(llm, memory, text, step, run, salt)
                if smaller:
                    steps[i:i + 1] = smaller
                    continue
        results.append(run.solution)
        i += 1
    out.solution = results[-1] if results else ""
    return out


def rollout_seed(llm, task, salt=""):
    """The untrained baseline: the same team machinery with an empty memory."""
    return rollout(llm, Memory(), task, salt=salt)
