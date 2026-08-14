"""Workflow Registry 与 Workflow 抽象测试。"""

import pytest

from app.core.errors import WorkflowNotFound
from app.workflows import SequentialWorkflow, Workflow, get_registry
from app.workflows.registry import WorkflowRegistry


class _FakeWorkflow(Workflow):
    name = "fake_workflow"
    version = "0.0.0"

    def execute(self, db, run_id):  # noqa: ANN001
        return {"ok": True}


def test_sequential_workflow_is_workflow_subclass() -> None:
    assert issubclass(SequentialWorkflow, Workflow)
    assert SequentialWorkflow.name == "sequential_report"
    assert SequentialWorkflow.version == "1.1.0"


def test_registry_register_and_get() -> None:
    reg = WorkflowRegistry()
    reg.register(_FakeWorkflow)
    assert reg.has("fake_workflow")
    assert reg.get("fake_workflow") is _FakeWorkflow


def test_registry_duplicate_raises() -> None:
    reg = WorkflowRegistry()
    reg.register(_FakeWorkflow)
    with pytest.raises(ValueError):
        reg.register(_FakeWorkflow)


def test_registry_unknown_raises() -> None:
    reg = WorkflowRegistry()
    with pytest.raises(WorkflowNotFound):
        reg.get("nope")


def test_global_registry_has_sequential() -> None:
    reg = get_registry()
    assert reg.has("sequential_report")
    assert reg.get("sequential_report") is SequentialWorkflow


def test_workflow_resume_and_cancel_not_implemented_by_default() -> None:
    wf = _FakeWorkflow()
    with pytest.raises(NotImplementedError):
        wf.resume(None, "run_x")
    with pytest.raises(NotImplementedError):
        wf.cancel(None, "run_x")
