"""Stage 1 checks. None of these call a model."""
import pytest

from agentforge.gate import gate
from agentforge.llm import ScriptedLLM
from agentforge.rollout import run_agent
from agentforge.sandbox import Workdir
from tasks import load_tasks

TASKS = load_tasks()
BY_ID = {t.id: t for t in TASKS}


def test_task_set_shape():
    assert len(TASKS) == 48
    assert len(load_tasks("train")) == 18
    assert len(load_tasks("heldout")) == 30
    assert len(BY_ID) == 48


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t.id)
def test_reference_passes_and_naive_fails(task):
    assert gate(task, task.ref).passed
    assert not gate(task, task.naive).passed


def test_digest_names_failures_without_expected_values():
    task = BY_ID["mu1"]
    result = gate(task, task.naive)
    assert "test_two_payments" in result.digest and "wrong result" in result.digest
    assert "1325" not in result.digest and "5997" not in result.digest


def test_gate_handles_broken_and_hanging_solutions():
    task = BY_ID["mu1"]
    assert "could not be loaded" in gate(task, "def broken(:").digest
    assert not gate(task, "").passed
    hang = "def record_payments(ledger, payments):\n    while True: pass\n"
    assert "did not finish" in gate(task, hang, timeout=2).digest


def test_sandbox_has_kiln_but_not_the_hidden_tests():
    with Workdir() as wd:
        assert wd.run("import kiln; print(kiln.sku(' a '))").strip() == "A"
        assert "ModuleNotFoundError" in wd.run("import tasks")
        assert "TimeoutError" in wd.run("while True: pass", timeout=1)


def test_rollout_runs_code_then_submits():
    task = BY_ID["slot1"]
    llm = ScriptedLLM([
        ScriptedLLM.call("run_python", code="import kiln; s = kiln.Shelf(1); s.put(1, 'a'); print(s.get(0), s.get(1))"),
        ScriptedLLM.call("submit", code=task.ref),
    ])
    run = run_agent(llm, "system", task.render())
    assert run.steps[0]["output"].strip() == "None a"
    assert run.rounds == 2 and not run.overflow
    assert gate(task, run.solution).passed


def test_running_out_of_rounds_is_an_overflow():
    llm = ScriptedLLM([ScriptedLLM.call("run_python", code="print(1)")] * 2
                      + [ScriptedLLM.call("submit", code="x = 1")])
    run = run_agent(llm, "system", "task", rounds=2)
    assert run.overflow and run.solution == "x = 1"
    assert llm.requests[-1]["force_tool"] == "submit"
