# How to explain this project

Notes for explaining AgentForge and the paper behind it to someone who has read neither. Everything here is backed by the numbers in the [README](README.md) and the [results page](docs/index.html).

## The 30-second version

> AI models are smart but don't know your house rules. A 2026 paper called EMMA says the best way to teach them is a notebook, where every mistake adds one small, checked lesson in the right section. I built a small version to test that. I invented a code library with hidden rules, let an AI agent practise on it, and compared a careful notebook against one the AI could rewrite freely. In my test the free-for-all version won clearly: 76% against 37%. The careful version's lessons were too vague, and nothing in either version could tell a true lesson from a false one.

## The 2-minute version

1. **The problem.** Picture a capable new hire at a company with unwritten rules. They keep getting things wrong because nobody told them the rules, not because they lack skill. AI models are in the same spot with anything they have not seen before. Retraining the model is slow and costly.
2. **The cheap fix.** Leave the model alone and give it a notebook it reads before each job. After a mistake, write a lesson in the notebook.
3. **The paper's idea.** The notebook has three sections: planning notes, specialists, and how-to cards called skills. A reviewer decides what kind of mistake happened, and that decides which section the lesson goes in. It may write one small lesson. A rule-checker, which is ordinary code, can refuse the lesson if it copies the answer, rewrites too much, or keeps changing the same place.
4. **The paper's claim.** This careful process beats letting the AI rewrite its notebook however it likes.
5. **My test.** I made up a small library, `kiln`, with six hidden rules, and 48 small programming tasks that need those rules. The agent practised on 18 and was tested on the other 30.
6. **What happened.** With no notebook the agent passed 38% of the time. The careful version: 37%. A careful version whose reviewer was told to be specific: 53%. The free-for-all version: 76%.
7. **Why.** The careful lessons came out vague. The free-for-all version learned more from each mistake and wrote the library's rules down plainly. And when a lesson was false, no version noticed.
8. **What it means.** It does not show the paper is wrong. My test was tiny, and the paper's limits are meant for long training on varied work, where a free-for-all notebook has time to become a mess. It does show the careful method has a real cost, and that checking a lesson's form is not the same as checking it is true.

## Plain words and the paper's words

| Plain words | The paper's term | In this repo |
|---|---|---|
| The notebook | Episodic memory | `agentforge/memory.py` |
| Planning notes | Controller memory | `Note` |
| Specialists | Agent pool | `Agent` |
| How-to cards | Skill pool | `Skill` |
| The reviewer | Reflector | `agentforge/reflector.py` |
| Kind of mistake | Failure scope | `SCOPES` |
| The rule-checker | Guards | `agentforge/guards.py` |
| The grader | Gate | `agentforge/gate.py` |
| One try at a task | Rollout | `agentforge/rollout.py` |
| Practice tasks and unseen tasks | Training split and held-out split | `tasks/` |
| Free-for-all learning | Ill-scoped evolution | the `unguarded` arm |
| The versions being compared | Arms | `seed`, `emma`, `emma-v2`, `unguarded` |

## The five kinds of mistake

| Kind | Example from this project | Where the lesson goes |
|---|---|---|
| One-off slip | Handed in experiment code instead of the answer | Nowhere. Try again |
| Bad working habit | Submitted without testing | The agent's standing instructions |
| Wrong or missing procedure | Did not know shelf slots start at 1 | A skill |
| Missing capability | Nobody on the team suits the work | A new skill or specialist |
| Bad planning | Split a tiny task into too many steps | A planning note |

## The five checks

| Check | Refuses a lesson that |
|---|---|
| Scope and action | Is the wrong kind of fix for the kind of mistake |
| Change of strategy | Is a third change to the same section after two that failed |
| No leakage | Names the task's own function or copies its wording |
| Prompt preservation | Throws away more than 40% of an agent's instructions |
| Bounded growth | Breaks a size limit, or points at something that does not exist |

## Numbers worth remembering

| Number | What it is |
|---|---|
| 6, 48, 18, 30 | Hidden rules, tasks, practice tasks, unseen tasks |
| 38% | No notebook, on unseen tasks |
| 37% | Careful version as first built |
| 53% | Careful version, reviewer told to be specific |
| 76% | Free-for-all version |
| 15 of 15 and 0 of 15 | The revised careful version on date ranges (true lesson) and on rates (false lesson) |
| 15 against 36 | Planning notes in the careful and free-for-all notebooks |

## Stories that make it concrete

- **The repeated mistake (stage 1).** Asked for the item in the first shelf slot, the untrained agent wrote `shelf.get(0)` every time. `kiln` numbers slots from 1. It failed all eight shelf tasks the same way.
- **A fact against a habit (stage 2).** One hand-written fact, "slots start at 1", fixed 7 of 8 shelf tasks and nothing else. One hand-written habit, "test before you submit", helped more widely but used 3.5 times the tokens. That is why the notebook has sections.
- **Pointing at nothing (stage 4).** The reviewer tried to revise a skill that did not exist. The check replied, "There is no skill named 'shelf-membership-check' to revise. Use create_skill." The reviewer fixed it and the lesson was accepted.
- **The wrong lesson that got credit (stage 5).** The reviewer wrote "divide the percentage by 100", which is wrong. The next attempt happened to pass anyway, so the lesson stayed. Run `python -m agentforge explain bp1` to see it.
- **True and false, equally confident (stage 6).** The revised careful notebook said, correctly, that date ranges leave out the end date, and passed 15 of 15. It also said, wrongly, that shelf slots start at zero, and passed 1 of 15.

## Questions people will ask

**So is the paper wrong?**
No. My test was far too small to say that. The paper trained across three public benchmarks and five models. I used one made-up library and 18 practice tasks. The paper's limits are meant to stop a notebook bloating over long training, and 18 tasks is not long enough for that to matter.

**Why did the careful version do so badly?**
Three reasons, in my reading. Its lessons were vague, because the reviewer was told to generalise and not copy the task. It was allowed one change per mistake while the free-for-all version made several. And one check, which forbids a third change to the same section, blocked it often, because I allowed only three tries per task where the paper allows five.

**Did you just build the careful version badly?**
Partly, and the project says so. The prompts and thresholds are mine, because the paper has no code release that I could find. That is why I trained a second careful version with one fix and reported both.

**What was the most surprising finding?**
That nothing in the system checks whether a lesson is true. The checks look at a lesson's form. A confident, well-formed, false lesson passes every one of them.

**Why a made-up library?**
Current AI models already know real libraries, so there would be nothing to learn. A made-up one guarantees the agent starts without the rules and that a lesson from one task can help on another.

**How do you know the results are not luck?**
Every unseen task was tried three times per version, and the page shows the range. The free-for-all version's lead is far bigger than the spread. The gap between no notebook and the first careful version is not, so I do not claim one beat the other.

**What would you do next?**
More practice tasks across several unrelated libraries, five tries per task, repeated training runs, and unseen tasks that use rules the practice tasks never touched. That last one would punish lessons that only fit the practice set.

**What did it cost?**
About $4 of OpenAI usage in total, using a small model for the workers and a mid-sized one for the reviewer.

## What to show

- The results page: https://austin-brock.github.io/AgentForge/
- One mistake told start to finish: `python -m agentforge explain bp1` (add `--arm unguarded` or `--arm emma-v2` for the other versions).
- The final table without spending anything: `python -m agentforge eval --show`.
- The saved evidence: everything under `runs/` (see the README section "Saved evidence").

## Explain-it-back checklist

This was the last step of the build plan and has not been done yet. To do it, answer each question out loud or in writing without looking, then compare with the section named.

1. What problem is the paper trying to solve? (The 2-minute version, points 1 and 2)
2. What are the three sections of the notebook, and why three? (Stories: a fact against a habit)
3. What does the reviewer decide, and what is it allowed to do? (The five kinds of mistake)
4. What can the rule-checker refuse, and what can it not check? (The five checks; most surprising finding)
5. What were the versions compared, and what one thing differed between them? (Plain words table, last row)
6. What were the four results? (Numbers worth remembering)
7. Why did the free-for-all version win here? (Questions: why did the careful version do so badly)
8. Why does that not show the paper is wrong? (Questions: so is the paper wrong)
9. What is one thing you would change to test it properly? (Questions: what would you do next)

If an answer is shaky, the stage sections of the README walk through the evidence for it.
