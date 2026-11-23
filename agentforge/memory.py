"""The three-level memory (paper Eq. 3): M = (controller notes, agent pool, skill pool).

It is plain text stored as JSON. The model's weights never change; this file is all that learns.
"""
import copy
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# p_0 in the paper: the generalist prompt. Every specialist inherits it.
GENERALIST_PROMPT = (
    "You are a Python programmer solving a task that uses the kiln library. "
    "You can run code with run_python in a sandbox where `import kiln` works. "
    "When your work on the step is ready, call submit."
)
GENERALIST = "generalist"


@dataclass
class Note:
    """Controller memory: a rule about how to split up and hand out work."""
    topic: str
    text: str
    generality: str = "general"  # general | domain_specific


@dataclass
class Agent:
    """A specialist. `prompt` holds only what is specific to its role."""
    name: str
    description: str  # what the controller sees when choosing an agent
    prompt: str


@dataclass
class Skill:
    """A short procedure for one class of sub-problem."""
    name: str
    when: str  # one line the controller sees: when to attach this skill
    body: str  # the full procedure, shown only to the agent doing the step


@dataclass
class Memory:
    generalist_prompt: str = GENERALIST_PROMPT
    notes: list = field(default_factory=list)
    agents: list = field(default_factory=list)
    skills: list = field(default_factory=list)

    def agent_names(self):
        return [GENERALIST] + [a.name for a in self.agents]

    def prompt_for(self, name):
        """Paper Eq. 4: a specialist's prompt is the generalist's plus its own."""
        for a in self.agents:
            if a.name == name:
                return f"{self.generalist_prompt}\n\n{a.prompt}"
        return self.generalist_prompt

    def skill(self, name):
        return next((s for s in self.skills if s.name == name), None)

    def agent_index(self):
        lines = [f"- {GENERALIST}: handles any step"]
        return "\n".join(lines + [f"- {a.name}: {a.description}" for a in self.agents])

    def skill_index(self):
        return "\n".join(f"- {s.name}: {s.when}" for s in self.skills) or "(none)"

    def apply(self, action, payload):
        """Return (new memory, directive) after one admissible edit. The original is untouched.

        The directive is non-empty only for revise_plan, which changes the next attempt and not memory.
        """
        m, p = copy.deepcopy(self), payload
        if action == "revise_plan":
            return m, p["directive"]
        if action == "create_skill":
            m.skills.append(Skill(p["name"], p["when"], p["body"]))
        elif action == "revise_skill":
            skill = m.skill(p["name"])
            skill.when, skill.body = p["when"], p["body"]
        elif action == "refine_prompt":
            if p["agent"] == GENERALIST:
                m.generalist_prompt = p["prompt"]
            else:
                next(a for a in m.agents if a.name == p["agent"]).prompt = p["prompt"]
        elif action == "create_agent":
            m.agents.append(Agent(p["name"], p["description"], p["prompt"]))
        elif action == "memory_note":
            m.notes.append(Note(p["topic"], p["text"], p["generality"]))
        return m, ""

    def size(self):
        """Total characters of learned text, a simple measure of how much memory has grown."""
        return len(self.to_json())

    def to_json(self):
        return json.dumps(asdict(self), indent=2)

    def save(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(self.to_json())

    @classmethod
    def from_dict(cls, data):
        return cls(
            generalist_prompt=data.get("generalist_prompt", GENERALIST_PROMPT),
            notes=[Note(**n) for n in data.get("notes", [])],
            agents=[Agent(**a) for a in data.get("agents", [])],
            skills=[Skill(**s) for s in data.get("skills", [])],
        )

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text()))
