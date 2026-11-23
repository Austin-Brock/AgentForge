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
| 2. Memory | The three-section notebook | Done |
| 3. Scoped reflection | A reviewer that assigns each failure to one section | Done |
| 4. Guards | The rule-checker that can refuse an edit | Done |
| 5. Training | The learning loop, and the anything-goes version | Done |
| 6. The experiment | The three-way comparison and a results page | Next |

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
| `python -m agentforge run` | Runs the agent team on every task with an empty notebook |
| `python -m agentforge run --memory examples/fact.json` | The same, with a notebook loaded from a file |
| `python -m agentforge reflect --run seed` | Has the reviewer diagnose every training failure in a saved run. Nothing is changed |
| `python -m agentforge reflect --run seed --guards` | The same, with each proposal checked by the guards and refused ones sent back for a rewrite |
| `python -m agentforge train --arm emma` | Runs the learning loop and saves the notebook it produces (`--arm unguarded` for the anything-goes version) |
| `python -m agentforge explain bp1` | Tells the story of one training task in plain language |
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

### Stage 2: the notebook

**What was built.** The memory, which is the only thing that will ever learn. It is a plain text file with three sections:

| Section | What it holds | Who reads it |
|---|---|---|
| Controller notes | Rules for splitting up and handing out work | The controller, when planning |
| Agent pool | Specialists, each inheriting the generalist's instructions plus its own | The agent doing a step |
| Skill pool | Short procedures, each with a one-line "use when" label | The controller sees the labels; the agent gets the full text |

The single agent from stage 1 became a small team: a controller plans the steps and picks an agent and skills for each, and the agent does the work. If an agent runs out of rounds, the controller splits its step into smaller ones.

**What was run.** All 48 tasks, three times, each with a different notebook written by hand:

- **Empty:** nothing in it. This is the real baseline for the later experiment.
- **Fact:** one skill saying shelf slots are numbered from 1 ([examples/fact.json](examples/fact.json)).
- **Habit:** one paragraph added to the generalist's instructions, telling it to test its code on small examples, including edge cases, before submitting ([examples/habit.json](examples/habit.json)).

**Result.**

| Notebook | Passed | Shelf tasks | Date-range tasks | Tested its code | Tokens used |
|---|---|---|---|---|---|
| Empty | 14 of 48 (29%) | 0 of 8 | 3 of 8 | 30 of 48 tasks | 366,000 |
| Fact | 20 of 48 (42%) | 7 of 8 | 2 of 8 | 34 of 48 tasks | 347,000 |
| Habit | 23 of 48 (48%) | 2 of 8 | 6 of 8 | 46 of 46 tasks | 1,278,000 |

**Findings.**

- A fact is narrow and reliable. The one skill took shelf tasks from 0 to 7 of 8 and cost nothing extra. The controller attached it to all eight shelf tasks, plus one product-code task that also uses a shelf, and to nothing else.
- A habit is broad and expensive. Testing before submitting helped across more rules, mainly date ranges, but used about three and a half times the tokens and made agents run out of rounds 27 times, against 4 with the empty notebook. It still missed most shelf tasks, because a test only helps if the agent picks an example that exposes the problem.
- The two lessons belong in different places. The fact is only useful when a shelf is involved, so it sits in a skill that is pulled out on demand. The habit applies to everything, so it sits in the instructions every agent reads. This is the reason the paper's memory has levels.
- The controller over-plans. It split every one of these small tasks into several steps, even though it was told to use one step unless the task had separable parts. Some solutions became over-built as a result. This is a planning problem, which is what the third section, controller notes, exists to fix. It has been left alone on purpose, for the learning loop to find.
- The team with an empty notebook (14 of 48) did no better than the single agent in stage 1 (17 of 48). More structure does not help by itself.

**What this shows about the paper.** This is Section 3.1: memory is split by how widely a lesson applies. A person chose where each lesson went here. The paper's contribution is doing that choice automatically and safely, which stages 3 and 4 build.

**Caveats.**

- Each notebook was run once, and run-to-run variation is large. The money tasks scored 4, 2 and 6 of 8 across the three runs, although neither notebook says anything about money. Differences of a few tasks are noise. The final experiment will repeat each run.
- In the habit run, OpenAI rejected two tasks with a content-policy error that looks spurious. They are counted as failures.

### Stage 3: the reviewer

**What was built.** The reflector: an AI reviewer that reads one failed attempt and does four things, following the paper. It finds the step that went wrong, assigns the failure to one of five types, writes the lesson so it applies beyond this one task, and proposes exactly one edit.

| Failure type | Meaning | Edits it may propose |
|---|---|---|
| Execution slip | Knew the method, slipped once | Retry with a hint, or nothing |
| Agent behaviour | A general working habit failed | Rewrite an agent's instructions |
| Procedure | The method for a kind of sub-problem was wrong or missing | Add or revise a skill |
| Missing capability | No agent suits this work | Add a skill or a specialist |
| Routing | The work was split up or handed out badly | Add a controller note, or retry with a hint |

The reviewer never sees the hidden tests. It sees the attempt and the names of the failed tests, and it can run up to three rounds of experiments in the sandbox to check its theory. In this stage its proposals are only recorded. Nothing is applied.

**What was run.** The reviewer diagnosed the 15 training-task failures from the empty-notebook run in stage 2, once with each of two models in the reviewer role.

**Result.**

| | Cheap reviewer (`gpt-5.4-nano`) | Stronger reviewer (`gpt-5.4-mini`) |
|---|---|---|
| Found the real cause (my reading of each diagnosis) | About 5 of 15 | About 8 of 15 |
| Proposed a usable "add a skill" edit | 0 of 15 | 11 of 15 |
| Tried to revise a skill that does not exist | 15 of 15 | 3 of 15 |
| Lesson named the task's own function | 8 of 15 | 1 of 15 |
| Failure types used | Procedure, 15 times | Procedure 14 times, agent behaviour once |

Examples from the stronger reviewer:

- **Right.** For a date-range failure: "`Ledger.between(start, end)` returns entries with dates `>= start` and `< end`; the end date is excluded. To include a final day, advance the upper bound to the next day."
- **Wrong.** For a merging failure: "Call the merge helper and return its result directly. Do not re-sort." The real rule is the opposite: the lists must be sorted *before* merging. The reviewer never tried unsorted input, so it never saw records being dropped.
- **Too drastic.** For another merging failure it proposed replacing the generalist's entire instructions with one new paragraph.

**Findings.**

- An unchecked reviewer is not safe to obey. Across the two reviewers, proposals pointed at things that do not exist, copied the task's own function into the "general" lesson, stated the opposite of the truth, and would have erased an agent's instructions. Each of these is something stage 4's guards are meant to catch, except one: a confident, well-formed, wrong lesson. Only re-running the task can expose that.
- The reviewer has to be made to investigate. In a first version it was allowed to experiment but not required to, and it ran an experiment on 2 of 34 failures and guessed the rest. Requiring it to reproduce the failure first is what produced the numbers above.
- The reviewer's model matters more than the workers'. The stronger model found more real causes and wrote lessons that were more general. From here on the reviewer uses `gpt-5.4-mini` and the workers stay on `gpt-5.4-nano`. The paper names pairing a strong reviewer with weaker workers as future work.
- Nearly everything was filed as "procedure". That fits these tasks, where most failures are a missing fact about `kiln`. But neither reviewer flagged the controller's over-planning from stage 2 as a routing problem, and one failure caused by a typo in the submitted code was filed as a procedure problem instead of a slip.
- The merging rule was found 0 times in 3 by either reviewer. It may be learned from a different task later, or not at all. That will show in the final results.

**What this shows about the paper.** This is Table 1 and the "reflect" step. The paper's phrase for what goes wrong without limits is "ill-scoped evolution": the model decides where and how much to change, so the result follows the model's habits. Both reviewers showed a habit here (file everything as a skill), and the cheap one showed several bad ones.

**Caveats.**

- "Found the real cause" is my own reading of 15 diagnoses per reviewer, not an automatic score. An automatic keyword score was tried and dropped because it counted wrong diagnoses as right.
- The first version of the reviewer was run once on all 34 failures, including held-out tasks, and its instructions were then changed. The changes were general (experiment before diagnosing; add versus revise) and say nothing about `kiln`, but strictly the held-out tasks were looked at once. The reviewer now only ever sees training tasks.
- A third model, `gpt-6-luna`, could not be tried because it does not support this project's way of calling tools.

### Stage 4: the guards

**What was built.** Five guards, written as ordinary code with no AI involved. Each proposed edit is checked against them in order. The first one it breaks refuses it, and the reason goes back to the reviewer, which may try again. After three refusals the outcome is "no change".

| Guard | What it refuses |
|---|---|
| Scope and action | An edit the diagnosed failure type does not allow, or one that is incomplete |
| Change of strategy | A third fix in a row at the same level of memory, after two that did not work |
| No leakage | A lesson that names the task's own function or copies its wording |
| Prompt preservation | A rewrite that keeps less than 60% of an agent's instructions, or that edits an agent that did not take part |
| Bounded growth | Anything over the size limits, a revision of something that does not exist, a duplicate name, or a new specialist that is not really a specialisation |

Size limits, scaled down from the paper's for this small task set: 6 agents, 20 skills, 15 notes, 2,000 characters per agent's instructions, 1,200 per skill.

The memory also gained the ability to apply an accepted edit, producing a new version and leaving the old one untouched.

**What was run.** The same 15 training failures as stage 3, with the stronger reviewer, this time with every proposal checked.

**Result.**

| Outcome | Count |
|---|---|
| Accepted first time | 11 of 15 |
| Refused, rewritten, then accepted | 4 of 15 |
| Given up as "no change" | 0 of 15 |

There were 5 refusals in total: 3 by bounded growth (revising a skill that does not exist), 1 by no leakage, 1 by prompt preservation.

Three of the refusals, as they happened:

- **Pointing at nothing.** Proposal: revise the skill `shelf-membership-check`. Refused: "There is no skill named 'shelf-membership-check' to revise. Use create_skill." The reviewer resubmitted it as a new skill and it was accepted.
- **Erasing instructions.** Proposal: replace the generalist's instructions with one paragraph. Refused: "The new prompt keeps 0% of the existing prompt's sentences; at least 60% must be kept word for word. Add to the prompt instead of replacing it." The reviewer dropped the idea and proposed a skill instead.
- **Copying the task.** Proposal: a skill whose text named the task's own function, `combine`. Refused for leakage. Its rewrite was refused too, for revising a skill that does not exist. On the third try the reviewer fell back to a one-off hint for the next attempt, which leaves memory untouched.

**Findings.**

- The guards caught every problem of form found in stage 3. After guarding, no accepted edit named its task's function, pointed at something missing, or erased an agent's instructions.
- Refusal reasons work as instructions. All four refused proposals were turned into admissible ones, and none had to be abandoned.
- A refusal can change the kind of fix, not only its wording. Twice the reviewer switched to a different, smaller edit after being refused.
- The guards do not check truth, and it shows. Several accepted lessons are wrong or beside the point. The merging lessons still miss the real rule, and one accepted shelf lesson says a lookup "can return a slot index even when the item is not present", which misreads what was observed. All of them passed, because they are well-formed, general and small.
- So the guards limit how much damage a bad lesson can do, and the re-run decides whether a lesson helped. That is the job of stage 5.

**What this shows about the paper.** This is Section 3.2.2 and Algorithm 3. The paper's point is that these limits are enforced by code, so they hold whichever model is proposing edits. The paper also states the weakness seen here: an accepted edit stays in memory even if the task still fails afterwards, so unhelpful entries can pile up.

**Caveats.**

- Each failure here was reviewed against an empty notebook, independently. In real training the notebook fills as it goes, so later failures meet earlier lessons. The change-of-strategy guard needs a history of failed fixes, so it was exercised only by the automated checks, not by this run.
- The leakage limit is 8 copied words, not the paper's 15, because these task descriptions are only one or two sentences long.
- The paper's guard thresholds came from a summarised reading of its appendix and are unconfirmed.

### Stage 5: training

**What was built.** The learning loop, which joins the earlier stages. For each training task, in a fixed order that mixes the six rules:

1. The team attempts the task and the grader marks it.
2. On a failure, the reviewer proposes a lesson, it is applied, and the team tries again, up to three times.
3. No lesson is written after the last failed attempt, because it could never be tested.
4. At the end of the task the reviewer may add planning notes.

Lessons accumulate, so each task starts with what earlier tasks taught.

Two versions share this loop and differ in one thing:

- **Careful (EMMA):** one lesson per failure, of a kind the failure type allows, checked by the guards. At most two planning notes per task, also checked.
- **Anything-goes (unguarded):** any number of changes per failure, anywhere in the notebook, applied as proposed. No limit on planning notes.

Both reviewers get the same evidence and may run the same experiments.

A third piece is the `explain` command, which reads the training log and tells the story of one task in plain language.

**What was run.** Each version trained once on the 18 training tasks, starting from an empty notebook.

**Result on the training tasks.**

| | Careful | Anything-goes |
|---|---|---|
| Passed first try | 8 | 11 |
| Passed after one or more lessons | 5 | 5 |
| Never passed | 5 | 2 |
| Total attempts | 42 | 31 |
| Reviews of a failure | 24 | 13 |
| Changes made after reviews | 21 (8 new skills, 8 skill rewrites, 5 one-off hints) | 30 (6 new skills, 3 skill rewrites, 10 notes, 11 one-off hints) |
| Proposals refused by a guard | 18 | Not applicable |
| Notebook at the end | 8 skills, 15 notes | 6 skills, 36 notes |
| Notebook size | 11,000 characters | 16,900 characters |
| Tokens used | 682,000 | 457,000 |

Neither version created a specialist or changed the generalist's instructions.

**The anything-goes version did better on the training tasks.** These are the tasks each version practised on with feedback, so this is not the experiment's result. Stage 6 measures both on the 30 unseen tasks.

**Findings.**

- The anything-goes lessons are concrete, and the careful ones came out vague. The anything-goes notebook says "kiln.Ledger.between(start, end) is start-inclusive and end-exclusive." The careful one says "Some date-range methods exclude items dated exactly on the start boundary", which names no function and gets the side wrong. My reading is that the careful reviewer over-corrected: told to generalise and forbidden from copying the task, it stripped out the specifics that made the lesson useful. That is a weakness in my reviewer instructions, and possibly a real cost of the no-leakage rule.
- One guard did most of the refusing, and it cost attempts. Of the 18 refusals, 13 were "change of strategy": after two failed skill edits in a row, a third was not allowed. The reviewer usually kept proposing skills anyway. Three reviews ended with nothing changed and others fell back to a one-off hint.
- A wrong lesson got credit. On the first rates task the careful reviewer wrote a skill saying to divide the percentage by 100. That is wrong (the rule is to multiply by 100), but the next attempt passed anyway, so the skill stayed. A later task rewrote it to "multiply by 10", still wrong, then failed, and the wrong skill is in the final notebook. Run `python -m agentforge explain bp1` to see the first half of this.
- The anything-goes notebook has the problems the guards exist to prevent. It holds three notes and a skill about one specific training task (`top_key`), two notes with the same name saying the same thing about date ranges, and one note that states something false about merging. It grew by 26 planning notes at task ends alone, and every note is offered to the controller on every task.
- The merging rule (sort before merging) was not learned by either version.
- The careful notebook stopped accepting planning notes at its limit of 15, refusing 9 more.

**What this shows about the paper.** This is Algorithm 1. The paper predicts the right-hand column's symptoms: unguarded learning follows the model's habits (here, writing a planning note about everything) and stores task-specific material. It also names the weakness seen in the left-hand column, that an accepted lesson persists whether or not it helped. What the paper does not predict is the careful version learning more slowly, and with vaguer lessons, on the training tasks themselves.

**Caveats.**

- One training run per version. Training is sequential and each step depends on the last, so a second run could go differently.
- The anything-goes version is my own design for "no scopes, no guards". It is not one of the paper's baseline systems.
- The limit of three revisions per task (the paper uses five) interacts with the change-of-strategy guard: with only three, the third can never be a skill edit if the first two were.

## How it differs from the paper

- One small made-up domain instead of three public benchmarks, and one model instead of five.
- OpenAI's `gpt-5.4-nano` for the controller and agents and `gpt-5.4-mini` for the reviewer. The paper uses one model for every role.
- Three revisions per training task instead of five, and smaller size limits.
- The controller is simpler than the paper's: it plans once and passes each step's result to the next, without re-planning after every step.
- Tasks, prompts and size limits are my own. The paper has no code release that I could find.
