"""Running an agent on a task.

Stage 1 has only the seed: one generalist agent with no memory. It works in a tool loop
(run code in the sandbox, then submit) with a cap on rounds.
"""
from dataclasses import dataclass, field

from agentforge.llm import tool
from agentforge.sandbox import Workdir

# p_0 in the paper: the generalist prompt that every later specialist inherits.
GENERALIST_PROMPT = (
    "You are a Python programmer solving a task that uses the kiln library. "
    "You can run code with run_python in a sandbox where `import kiln` works. "
    "When your solution is ready, call submit with the full source of the solution module."
)

TOOLS = [
    tool("run_python", "Run a Python script in the sandbox and return its output.",
         code="The script to run."),
    tool("submit", "Hand in the final solution. Ends the task.",
         code="Full source of the solution module."),
]

ROUNDS = 8


@dataclass
class AgentRun:
    solution: str = ""
    steps: list = field(default_factory=list)  # [{"code": ..., "output": ...}]
    rounds: int = 0
    overflow: bool = False  # ran out of rounds before submitting


def run_agent(llm, system_prompt, task_text, rounds=ROUNDS, salt=""):
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
        # Out of rounds: record the overflow and take whatever the agent has.
        run.overflow = True
        messages.append({"role": "user", "content": "You are out of rounds. Submit your best solution now."})
        reply = llm.chat(messages, tools=TOOLS, force_tool="submit", salt=salt)
        for call in reply.tool_calls:
            if call.name == "submit":
                run.solution = call.args.get("code", "")
    return run


def rollout_seed(llm, task, salt=""):
    """The untrained baseline: the generalist alone, with empty memory."""
    return run_agent(llm, GENERALIST_PROMPT, task.render(), salt=salt)
