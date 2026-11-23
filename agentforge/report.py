"""Build the self-contained results page (docs/index.html) from the saved runs."""
import html
import json
from pathlib import Path

from agentforge.evaluate import ARM_LABELS, ARMS, load_results, load_usage, summarize_arm
from agentforge.explain import explain
from agentforge.memory import Memory
from tasks import FAMILY_LABELS, load_tasks

# Colour follows the version, never its rank. Three categorical slots (validated all-pairs,
# light and dark) plus a neutral for the untrained baseline.
ARM_VAR = {"seed": "--neutral", "emma": "--series-1", "unguarded": "--series-2", "emma-v2": "--series-3"}
RULE_SHORT = {"minor_units": "Money in cents", "windows": "Date ranges", "slots": "Shelf slots",
              "rates": "Rates", "merging": "Merging", "skus": "Product codes"}
HEAT = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"]  # one hue, light to dark

CSS = """
:root { color-scheme: light dark; }
.viz-root { --surface-1:#fcfcfb; --surface-2:#f3f2ef; --text-primary:#0b0b0b; --text-secondary:#52514e;
  --text-muted:#75746f; --grid:#e3e2de; --neutral:#8f8e88; --series-1:#2a78d6; --series-2:#eb6834;
  --series-3:#1baf7a; --good:#0ca30c; --critical:#d03b3b; }
@media (prefers-color-scheme: dark) { .viz-root { --surface-1:#1a1a19; --surface-2:#262624;
  --text-primary:#f0efec; --text-secondary:#c3c2b7; --text-muted:#9b9a92; --grid:#383835; --neutral:#8f8e88;
  --series-1:#3987e5; --series-2:#d95926; --series-3:#199e70; --good:#0ca30c; --critical:#e66767; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--surface-1); }
.viz-root { background:var(--surface-1); color:var(--text-primary); min-height:100vh;
  font:16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
main { max-width:860px; margin:0 auto; padding:40px 20px 80px; }
h1 { font-size:30px; line-height:1.2; margin:0 0 8px; }
h2 { font-size:21px; margin:44px 0 10px; }
h3 { font-size:16px; margin:24px 0 6px; }
p, li { color:var(--text-primary); } .lede { font-size:18px; color:var(--text-secondary); margin:0 0 20px; }
.muted { color:var(--text-muted); font-size:14px; }
a { color:var(--series-1); }
.card { background:var(--surface-2); border-radius:10px; padding:16px 18px; margin:14px 0; }
.tiles { display:flex; flex-wrap:wrap; gap:12px; margin:18px 0; }
.tile { flex:1 1 170px; background:var(--surface-2); border-radius:10px; padding:14px 16px; }
.tile b { display:block; font-size:30px; line-height:1.1; } .tile span { color:var(--text-secondary); font-size:14px; }
.swatch { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:7px; }
table { border-collapse:collapse; width:100%; font-size:14px; margin:10px 0; }
th, td { text-align:left; padding:7px 9px; border-bottom:1px solid var(--grid); vertical-align:top; }
th { color:var(--text-secondary); font-weight:600; } td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
.scroll { overflow-x:auto; }
td.heat { text-align:center; font-variant-numeric:tabular-nums; border:2px solid var(--surface-1); border-radius:4px; }
svg text { fill:var(--text-secondary); font-size:12.5px; } svg .strong { fill:var(--text-primary); font-weight:600; }
.pass { color:var(--good); font-weight:600; } .fail { color:var(--critical); font-weight:600; }
.edit { color:var(--text-secondary); }
pre { background:var(--surface-2); border-radius:10px; padding:14px 16px; overflow-x:auto; font-size:13px;
  line-height:1.5; white-space:pre-wrap; }
details { margin:8px 0; } summary { cursor:pointer; font-weight:600; }
#tip { position:fixed; pointer-events:none; background:var(--text-primary); color:var(--surface-1); padding:6px 9px;
  border-radius:6px; font-size:13px; max-width:280px; display:none; z-index:9; }
ol.steps li { margin:6px 0; }
"""

JS = """
const tip = document.getElementById('tip');
document.addEventListener('mousemove', e => {
  const t = e.target.closest('[data-tip]');
  if (!t) { tip.style.display = 'none'; return; }
  tip.textContent = t.dataset.tip; tip.style.display = 'block';
  tip.style.left = Math.min(e.clientX + 14, innerWidth - 300) + 'px'; tip.style.top = (e.clientY + 14) + 'px';
});
"""


def esc(text):
    return html.escape(str(text))


def pct(x):
    return f"{100 * x:.0f}%"


def bar_chart(summaries):
    """Horizontal bars: mean pass rate per version, with one dot per repeat to show the spread."""
    left, width, row, top = 190, 520, 46, 26
    h = top + row * len(summaries) + 26
    out = [f'<svg viewBox="0 0 {left + width + 70} {h}" role="img" width="100%" '
           f'aria-label="Pass rate on unseen tasks by version">']
    for tick in (0, 25, 50, 75, 100):
        x = left + width * tick / 100
        out.append(f'<line x1="{x}" y1="{top - 8}" x2="{x}" y2="{h - 22}" stroke="var(--grid)" stroke-width="1"/>'
                   f'<text x="{x}" y="{h - 6}" text-anchor="middle">{tick}%</text>')
    for i, (arm, s) in enumerate(summaries.items()):
        y = top + row * i
        w = max(width * s["rate"], 2)
        color = f"var({ARM_VAR[arm]})"
        tip = (f"{ARM_LABELS[arm]}: {pct(s['rate'])} ({s['passed']} of {s['attempts']} attempts). "
               f"Repeats: {', '.join(pct(r) for r in s['per_repeat'])}.")
        out.append(f'<text x="{left - 12}" y="{y + 14}" text-anchor="end" class="strong">{esc(ARM_LABELS[arm])}</text>')
        out.append(f'<g data-tip="{esc(tip)}"><rect x="{left}" y="{y - 6}" width="{width}" height="32" fill="transparent"/>'
                   f'<path d="M{left},{y} h{w - 4} a4,4 0 0 1 4,4 v12 a4,4 0 0 1 -4,4 h-{w - 4} z" fill="{color}"/>')
        for r in s["per_repeat"]:
            out.append(f'<circle cx="{left + width * r}" cy="{y + 10}" r="4.5" fill="var(--text-primary)" '
                       f'stroke="var(--surface-1)" stroke-width="2"/>')
        out.append(f'<text x="{left + width * max(s["rate"], s["high"]) + 12}" y="{y + 14}" class="strong">'
                   f'{pct(s["rate"])}</text></g>')
    out.append("</svg>")
    return "".join(out)


def growth_chart(series):
    """Lines: notebook size after each training task. `series` maps arm -> list of sizes."""
    left, width, top, height = 56, 560, 14, 200
    n = max(len(v) for v in series.values())
    peak = max(max(v) for v in series.values()) or 1
    top_tick = (int(peak / 5000) + 1) * 5000
    x = lambda i: left + width * i / max(n - 1, 1)
    y = lambda v: top + height * (1 - v / top_tick)
    out = [f'<svg viewBox="0 0 {left + width + 170} {top + height + 40}" role="img" width="100%" '
           f'aria-label="Notebook size after each training task">']
    for k in range(0, top_tick + 1, 5000):
        out.append(f'<line x1="{left}" y1="{y(k)}" x2="{left + width}" y2="{y(k)}" stroke="var(--grid)"/>'
                   f'<text x="{left - 8}" y="{y(k) + 4}" text-anchor="end">{k:,}</text>')
    for i in range(0, n, 3):
        out.append(f'<text x="{x(i)}" y="{top + height + 18}" text-anchor="middle">{i + 1}</text>')
    out.append(f'<text x="{left + width / 2}" y="{top + height + 36}" text-anchor="middle">training task</text>')
    ends = sorted(series, key=lambda a: series[a][-1])
    label_y = {}
    for a in ends:  # keep end labels at least 15px apart
        want = y(series[a][-1]) + 4
        label_y[a] = min(want, min(label_y.values()) - 15) if label_y else want
    for arm, values in series.items():
        color = f"var({ARM_VAR[arm]})"
        points = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(values))
        out.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2" '
                   f'stroke-linejoin="round" stroke-linecap="round"/>')
        for i, v in enumerate(values):
            out.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="7" fill="transparent" '
                       f'data-tip="{esc(ARM_LABELS[arm])}, after task {i + 1}: {v:,} characters"/>')
        out.append(f'<circle cx="{x(len(values) - 1)}" cy="{y(values[-1])}" r="4" fill="{color}" '
                   f'stroke="var(--surface-1)" stroke-width="2"/>'
                   f'<text x="{x(len(values) - 1) + 10}" y="{label_y[arm]}" class="strong">{esc(ARM_LABELS[arm])}</text>')
    out.append("</svg>")
    return "".join(out)


def heat_table(summaries):
    head = "".join(f"<th class='num'>{esc(RULE_SHORT[f])}</th>" for f in FAMILY_LABELS)
    rows = []
    for arm, s in summaries.items():
        cells = []
        for fam in FAMILY_LABELS:
            c = s["families"].get(fam, {"passed": 0, "attempts": 0})
            rate = c["passed"] / c["attempts"] if c["attempts"] else 0
            step = min(int(rate * len(HEAT)), len(HEAT) - 1)
            ink = "#ffffff" if step >= 3 else "#0b0b0b"
            cells.append(f'<td class="heat" style="background:{HEAT[step]};color:{ink}" '
                         f'data-tip="{esc(ARM_LABELS[arm])}, {esc(FAMILY_LABELS[fam])}: {c["passed"]} of '
                         f'{c["attempts"]} attempts passed">{pct(rate)}</td>')
        rows.append(f"<tr><th>{esc(ARM_LABELS[arm])}</th>{''.join(cells)}</tr>")
    return f"<div class='scroll'><table><tr><th></th>{head}</tr>{''.join(rows)}</table></div>"


def timeline(events):
    """One row per training task: each attempt as pass/fail with the edits made between attempts."""
    rows, current = [], None
    for e in events:
        if e["type"] == "attempt":
            if current is None or current["task"] != e["task"]:
                current = {"task": e["task"], "family": e["family"], "cells": []}
                rows.append(current)
            mark = '<span class="pass">✓ pass</span>' if e["passed"] else '<span class="fail">✗ fail</span>'
            current["cells"].append(mark)
        elif e["type"] == "reflection":
            actions = ", ".join(x["action"].replace("_", " ") for x in e["edits"]) or "no change"
            scope = f"{e['scope'].replace('_', ' ')}: " if e["scope"] else ""
            refused = f" ({len(e['refusals'])} refused)" if e["refusals"] else ""
            current["cells"].append(f'<span class="edit">→ {esc(scope + actions + refused)} →</span>')
        elif e["type"] == "task_end" and e["notes_added"]:
            current["cells"].append(f'<span class="muted">+{len(e["notes_added"])} note(s)</span>')
    body = "".join(f"<tr><td>{esc(r['task'])}</td><td>{esc(RULE_SHORT[r['family']])}</td>"
                   f"<td>{' '.join(r['cells'])}</td></tr>" for r in rows)
    return f"<div class='scroll'><table><tr><th>Task</th><th>Rule</th><th>What happened</th></tr>{body}</table></div>"


def notebook(memory):
    parts = []
    for s in memory.skills:
        parts.append(f"<tr><td>Skill</td><td><b>{esc(s.name)}</b><br><span class='muted'>Use when: {esc(s.when)}</span>"
                     f"<br>{esc(s.body)}</td></tr>")
    for n in memory.notes:
        parts.append(f"<tr><td>Note</td><td><b>{esc(n.topic)}</b><br>{esc(n.text)}</td></tr>")
    for a in memory.agents:
        parts.append(f"<tr><td>Specialist</td><td><b>{esc(a.name)}</b><br>{esc(a.prompt)}</td></tr>")
    return f"<div class='scroll'><table>{''.join(parts) or '<tr><td>Empty</td></tr>'}</table></div>"


def pick_story(events):
    """A training task whose story shows the whole loop: a failure, a refusal, an accepted edit, a pass."""
    by_task = {}
    for e in events:
        if "task" in e:
            by_task.setdefault(e["task"], []).append(e)
    def score(es):
        end = next((e for e in es if e["type"] == "task_end"), {})
        refl = [e for e in es if e["type"] == "reflection"]
        return (bool(end.get("passed")) and bool(refl), any(e["refusals"] for e in refl), -len(es))
    best = max(by_task, key=lambda t: score(by_task[t]), default=None)
    return best if best and score(by_task[best])[0] else None


def build(out_path="docs/index.html", findings_path="report_findings.md"):
    results = load_results()
    if not results:
        raise SystemExit("No evaluation results yet. Run `python -m agentforge eval` first.")
    summaries = {arm: summarize_arm(rows) for arm, rows in results.items()}
    trained = [a for a in summaries if ARMS[a]]
    events = {a: [json.loads(l) for l in Path(f"runs/train-{a}/events.jsonl").read_text().splitlines()] for a in trained}
    memories = {a: Memory.load(ARMS[a]) for a in trained}
    tasks = {t.id: t for t in load_tasks()}
    n_tasks = next(iter(summaries.values()))["tasks"]
    repeats = len(next(iter(summaries.values()))["per_repeat"])
    usage = load_usage()

    ranked = sorted(summaries, key=lambda a: -summaries[a]["rate"])
    tiles = "".join(
        f'<div class="tile"><b>{pct(summaries[a]["rate"])}</b><span><i class="swatch" '
        f'style="background:var({ARM_VAR[a]})"></i>{esc(ARM_LABELS[a])}</span></div>' for a in summaries)

    result_rows = "".join(
        f"<tr><th><i class='swatch' style='background:var({ARM_VAR[a]})'></i>{esc(ARM_LABELS[a])}</th>"
        f"<td class='num'>{pct(s['rate'])}</td><td class='num'>{pct(s['low'])} to {pct(s['high'])}</td>"
        f"<td class='num'>{s['passed']} of {s['attempts']}</td><td class='num'>{s['tasks_always']}</td>"
        f"<td class='num'>{s['tasks_never']}</td>"
        f"<td class='num'>{(usage[a]['input'] + usage[a]['output']) // s['attempts']:,}</td></tr>"
        if a in usage else "" for a, s in summaries.items())

    book_rows = "".join(
        f"<tr><th>{esc(ARM_LABELS[a])}</th><td class='num'>{len(m.skills)}</td><td class='num'>{len(m.notes)}</td>"
        f"<td class='num'>{len(m.agents)}</td><td class='num'>{m.size():,}</td>"
        f"<td class='num'>{sum(e['executions'] for e in events[a] if e['type'] == 'task_end')}</td>"
        f"<td class='num'>{sum(len(e['refusals']) for e in events[a] if e['type'] == 'reflection')}</td></tr>"
        for a, m in memories.items())

    growth = {a: [e["memory_size"] for e in events[a] if e["type"] == "task_end"] for a in trained}

    story_arm = next((a for a in ("emma-v2", "emma") if a in events and pick_story(events[a])), None)
    story = ""
    if story_arm:
        task_id = pick_story(events[story_arm])
        story = (f"<h2>One mistake, start to finish</h2><p>This is a real training task from the "
                 f"“{esc(ARM_LABELS[story_arm])}” version, told from its log. It shows every part of the loop: the "
                 f"failed attempt, the reviewer's diagnosis, a refused lesson where there was one, the accepted "
                 f"lesson, and the retry.</p><pre>{esc(explain(tasks[task_id], events[story_arm], story_arm))}</pre>")

    findings = ""
    if Path(findings_path).exists():
        items = [l[2:].strip() for l in Path(findings_path).read_text().splitlines() if l.startswith("- ")]
        findings = "<h2>What we found</h2><ul>" + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>"

    timelines = "".join(f"<details><summary>{esc(ARM_LABELS[a])}: training, task by task</summary>{timeline(events[a])}"
                        f"</details>" for a in trained)
    notebooks = "".join(f"<details><summary>{esc(ARM_LABELS[a])}: the finished notebook</summary>{notebook(m)}</details>"
                        for a, m in memories.items())
    v2_note = ("<li><b>Careful, revised reviewer:</b> the careful version trained a second time with one change: the "
               "reviewer was told to name the tool involved and say exactly what it does. This was added after the "
               "first careful notebook came out vague. Both are shown so nothing is hidden.</li>"
               if "emma-v2" in summaries else "")

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>AgentForge: can an AI agent learn the house rules?</title><style>{CSS}</style></head>
<body><div class="viz-root"><main>
<h1>Can an AI agent learn the house rules?</h1>
<p class="lede">A small test of one idea from a 2026 research paper: that an AI gets better at a job most reliably
when each mistake teaches it one small, checked lesson, written in the right place.</p>

<div class="tiles">{tiles}</div>
<p class="muted">Share of attempts passed on {n_tasks} tasks none of the versions had seen, each tried {repeats} times.
Best: {esc(ARM_LABELS[ranked[0]])}.</p>

<h2>The idea in plain words</h2>
<p>Imagine a capable new hire at a company with unwritten rules. Nobody told them that “until Friday” means
“until Thursday night”, so they keep getting things wrong. They are not short of skill. They are short of
local knowledge.</p>
<p>AI models are in the same position when they work with something they have never seen. Retraining the model
to teach it is slow and expensive. The cheaper way is to leave the model alone and give it a <b>notebook</b> that
it reads before each job.</p>
<p>The paper, <a href="https://arxiv.org/abs/2610.35966">EMMA</a>, is about how that notebook should be written.
It has three sections:</p>
<ul>
<li><b>Planning notes:</b> how to split up a job and who should do which part.</li>
<li><b>Specialists:</b> team members with extra instructions for one kind of work.</li>
<li><b>Skills:</b> short how-to cards, pulled out only when they apply.</li>
</ul>
<p>After each mistake a <b>reviewer</b> decides what kind of mistake it was. That decides which section the lesson
belongs in. The reviewer may write exactly one small lesson. Then a <b>rule-checker</b>, which is ordinary code and
not an AI, can refuse the lesson if it copies the answer to that one job, rewrites too much at once, or keeps
changing the same place without success.</p>
<p>The paper's claim is that this careful process beats letting the AI rewrite its own notebook however it likes.</p>

<h2>The experiment</h2>
<p>We invented a small code library called <code>kiln</code> with six unwritten rules, so no AI could already know
them. For example, its date ranges silently leave out the last day. We wrote 48 small programming tasks that can
only be solved by knowing a rule. Each version practised on 18 of them, then was tested on the other {n_tasks}
with its notebook frozen.</p>
<ul>
<li><b>No notebook:</b> the untrained agent. The baseline.</li>
<li><b>Careful (EMMA):</b> one lesson per mistake, checked by the rule-checker.</li>
<li><b>Anything-goes:</b> the reviewer may change anything, as much as it likes, with no checks.</li>
{v2_note}
</ul>

<h2>What we checked along the way</h2>
<p>Before the main experiment, four smaller tests each checked one piece of the idea.</p>
<ol class="steps">
<li><b>The agent really does not know the rules.</b> Untrained, it passed 17 of 48 tasks and kept repeating the same
mistakes. It failed all 8 shelf tasks the same way, by treating the first slot as slot 0 when the library counts
from 1.</li>
<li><b>Where a lesson is written matters.</b> We wrote two lessons by hand. A fact, “shelf slots start at 1”, stored
as a how-to card, fixed 7 of 8 shelf tasks and nothing else, at no extra cost. A habit, “test before you submit”,
added to the agent's standing instructions, lifted the total from 14 to 23 of 48 but took about three and a half
times as much computing.</li>
<li><b>An unchecked reviewer cannot be trusted.</b> Reviewing 15 failures, a cheap AI reviewer found the real cause
about 5 times and a stronger one about 8 times, by our reading. Some proposals pointed at things that did not
exist, some copied one task's answer into a “general” lesson, and one would have erased an agent's instructions.</li>
<li><b>The rule-checker catches bad form but not falsehood.</b> On the same 15 failures it accepted 11 lessons first
time and 4 more after sending them back with a reason. Several of the accepted lessons were still wrong.</li>
</ol>
<p class="muted">The evidence for each of these is in the
<a href="https://github.com/Austin-Brock/AgentForge#results-and-findings-stage-by-stage">stage-by-stage write-up</a>.</p>

<h2>Results on the unseen tasks</h2>
{bar_chart(summaries)}
<p class="muted">Bars show the average over {repeats} repeats. Each dot is one repeat, so the spread of the dots shows
how much a single run can vary. Hover for the numbers.</p>
<div class="scroll"><table><tr><th>Version</th><th class="num">Pass rate</th><th class="num">Range over repeats</th>
<th class="num">Attempts passed</th><th class="num">Tasks always passed</th><th class="num">Tasks never passed</th>
<th class="num">Tokens per attempt</th></tr>{result_rows}</table></div>

<h3>By unwritten rule</h3>
{heat_table(summaries)}
<p class="muted">Share of attempts passed for the tasks built on each rule. Darker is higher.</p>
{findings}

<h2>What each version learned</h2>
<div class="scroll"><table><tr><th>Version</th><th class="num">Skills</th><th class="num">Planning notes</th>
<th class="num">Specialists</th><th class="num">Size (characters)</th><th class="num">Training attempts</th>
<th class="num">Lessons refused</th></tr>{book_rows}</table></div>
<h3>Notebook size during training</h3>
{growth_chart(growth)}
<p class="muted">Characters of text in the notebook after each of the 18 training tasks.</p>
{notebooks}
{story}

<h2>Training, task by task</h2>
<p>Each row is one practice task. Arrows show what the reviewer changed between attempts.</p>
{timelines}

<h2>Limits of this test</h2>
<ul>
<li>It is one small made-up library and {n_tasks} test tasks, with each version trained once. The paper used three
public benchmarks and five AI models. This is a test of the idea, not a reproduction of the paper's numbers.</li>
<li>Results vary from run to run, which is why every test task was tried {repeats} times. Small gaps between
versions should not be read as real differences.</li>
<li>The anything-goes version is our own design, not one of the paper's comparison systems.</li>
<li>Workers used OpenAI's gpt-5.4-nano and the reviewer used gpt-5.4-mini. The paper uses one model for every role.</li>
</ul>
<h2>More</h2>
<ul>
<li><a href="https://github.com/Austin-Brock/AgentForge">The code and full write-up</a>, with results, findings and
caveats for every stage, and a table matching each part of the paper to the code.</li>
<li><a href="https://github.com/Austin-Brock/AgentForge#about-the-paper">What the paper set out to do</a>, how its
authors tested it, and what they reported.</li>
<li><a href="https://github.com/Austin-Brock/AgentForge/blob/main/EXPLAINING.md">A plain-language guide</a> with
short and long explanations, a glossary, and answers to likely questions.</li>
<li><a href="https://github.com/Austin-Brock/AgentForge#saved-evidence">The saved evidence</a>: every attempt, every
reviewer diagnosis, the training logs, the notebooks, and the raw model replies.</li>
</ul>
<p class="muted">Built with AgentForge. Paper: Niu, Liu, Yu and Klinkner, “EMMA: Structured Episodic Memory for
Multi-Agent Workflow Synthesis”, 2026.</p>
</main><div id="tip"></div></div><script>{JS}</script></body></html>"""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(page)
    return out_path
