"""The gate: run a task's hidden tests against a solution and return a pass/fail verdict
plus a short digest (the paper's Gate(q, y) = (v, d)).

The digest names the failed tests and the kind of error. It never includes the values the
tests expected, so it cannot leak the answer into memory.
"""
import json
from dataclasses import dataclass, field

from agentforge.sandbox import Workdir

_MARK = "@@GATE"
_RUNNER = r'''
import json, sys
MARK = "@@GATE"
ns = {}
try:
    import kiln
    from datetime import date, timedelta
    import solution
    ns.update(vars(solution))
    ns.update(kiln=kiln, date=date, timedelta=timedelta)
    exec(open("hidden_tests.py").read(), ns)
except BaseException as e:
    print(MARK + json.dumps({"load_error": f"{type(e).__name__}: {e}"[:200]}))
    sys.exit(0)
results = []
for name, fn in list(ns.items()):
    if name.startswith("test_") and callable(fn):
        try:
            fn()
            results.append([name, None])
        except AssertionError:
            results.append([name, "wrong result"])
        except BaseException as e:
            results.append([name, f"{type(e).__name__}: {e}"[:160]])
print(MARK + json.dumps({"results": results}))
'''


@dataclass
class GateResult:
    passed: bool
    digest: str
    failed: list = field(default_factory=list)
    total: int = 0


def gate(task, solution, timeout=20):
    if not (solution or "").strip():
        return GateResult(False, "No solution was submitted.")
    with Workdir() as wd:
        wd.write("solution.py", solution)
        wd.write("hidden_tests.py", task.tests)
        out = wd.run(_RUNNER, timeout=timeout)
    line = next((l for l in reversed(out.splitlines()) if l.startswith(_MARK)), None)
    if line is None:
        return GateResult(False, "The tests did not finish (crash or timeout).")
    data = json.loads(line[len(_MARK):])
    if "load_error" in data:
        return GateResult(False, f"The solution could not be loaded: {data['load_error']}")
    results = data["results"]
    failed = [(name, why) for name, why in results if why]
    if not failed:
        return GateResult(True, f"All {len(results)} tests passed.", [], len(results))
    detail = "; ".join(f"{name} ({why})" for name, why in failed)
    digest = f"{len(failed)} of {len(results)} tests failed: {detail}"
    return GateResult(False, digest, [name for name, _ in failed], len(results))
