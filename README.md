# AgentForge

An EMMA-inspired coding agent that learns from failed tests by updating its routing rules, specialist instructions, or reusable skills, then measures whether those changes help on unseen tasks.

It is a small-scale test of the idea in [EMMA: Structured Episodic Memory for Multi-Agent Workflow Synthesis](https://arxiv.org/abs/2610.35966) (Niu, Liu, Yu, Klinkner, 2026). It is not a reproduction of the paper's published numbers.

## The idea in one minute

A capable AI model can still fail at a job because nobody told it the house rules. Retraining the model to teach it those rules is expensive. The cheaper option is to leave the model alone and write the lessons down as text it reads next time.

The paper's claim is about *where* and *how* each lesson gets written:

- Lessons go in a notebook with three sections: how to plan the work, which specialist handles what, and step-by-step procedures.
- Each failure is assigned to exactly one section, and earns exactly one small edit.
- A rule-checker, written as ordinary code, can refuse an edit that copies the answer, rewrites too much, or keeps changing the same place.

The paper says this beats letting the AI rewrite its own notebook however it likes. AgentForge tests that by comparing three versions of the same agent on tasks none of them has seen: one with no notebook, one with the careful notebook, and one with an anything-goes notebook.

## Status

| Stage | What it builds | Status |
|---|---|---|
| 1. The problem | A made-up library with unwritten rules, 48 tasks, a grader, an untrained agent | Done |
| 2. Memory | The three-section notebook | Next |
| 3. Scoped reflection | A reviewer that assigns each failure to one section | Not started |
| 4. Guards | The rule-checker that can refuse an edit | Not started |
| 5. Training | The learning loop, and the anything-goes version | Not started |
| 6. The experiment | The three-way comparison and a results page | Not started |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # add your OpenAI key
python -m agentforge models # check the model ID in .env exists on your account
```

Commands so far:

| Command | What it does |
|---|---|
| `python -m agentforge check-tasks` | Checks the task set without calling a model |
| `python -m agentforge show win1` | Prints one task exactly as the agent sees it |
| `python -m agentforge calibrate` | Runs the untrained agent on every task |
| `pytest` | Runs the automated checks (no model calls) |

The agent's code runs on your machine in a throwaway folder with a timeout. That is isolation for convenience, not a security boundary.

## Results and findings, stage by stage

### Stage 1: the problem

**What was built.** `kiln` is a made-up inventory and ledger library, so no model has seen it before. It has six rules that its documentation does not mention. There are 48 tasks, 8 per rule, each asking for one small Python function. Each task has hidden tests, a correct solution that passes them, and a "fell for the trap" solution that fails them. 18 tasks are for training and 30 are held out.

**What was run.** The untrained agent (`gpt-5.4-nano`, one generalist, no memory) attempted all 48 tasks once. It could try code in a sandbox for up to 8 rounds before submitting.

**Result: 17 of 48 passed (35%).**

| Unwritten rule | Passed |
|---|---|
| Money is stored in whole cents | 7 of 8 |
| Product codes must be tidied before lookup | 6 of 8 |
| Date ranges leave out the end date | 2 of 8 |
| Rates are in hundredths of a percent | 1 of 8 |
| Merging two lists needs both sorted | 1 of 8 |
| Shelf slots are numbered from 1 | 0 of 8 |

**Findings.**

- The same mistake repeats across tasks. All eight shelf tasks failed on one wrong assumption: the agent wrote `shelf.get(0)` for the first slot, the normal Python habit, where `kiln` wants `shelf.get(1)`.
- The agent rarely checks its work. On 33 of 48 tasks it submitted without running any code.
- Two rules were easy to guess. Storing money in cents is a common convention, and the product-code tasks hint at the rule in their wording. Most of the room to improve is in the other four.
- One failure was a plain slip, not missing knowledge: on `sku5` the agent submitted its experiment code instead of a solution.
- The run used about 60,000 tokens.

**What this shows about the paper.** This is the paper's starting point (Sections 1 and 2): a capable model failing repeatedly for lack of local knowledge. The three kinds of failure above also point at the paper's main question. "Slots start at 1" is a fact about one tool, "run your code before submitting" is a habit for every task, and the `sku5` slip should not become a permanent lesson at all. Deciding which is which is what the later stages build.

**Caveat.** This is a single run per task, so the per-rule counts will vary somewhat between runs.

## How it differs from the paper

- One small made-up domain instead of three public benchmarks, and one model instead of five.
- OpenAI's `gpt-5.4-nano` instead of the paper's models.
- Tasks, prompts and size limits are my own. The paper has no code release that I could find.
