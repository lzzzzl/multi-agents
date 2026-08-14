"""挂起/恢复测试。"""

from unittest.mock import MagicMock, patch

from app.llms.mock import MockLLMProvider
from app.models import Run, Task
from app.workflows import SequentialWorkflow
from app.workflows.checkpoint import WorkflowSuspended


_NODE_BY_AGENT = {
    "agent_planner": "plan",
    "agent_researcher": "research",
    "agent_writer": "compose",
    "agent_reviewer": "compose",
}


class SuspendingWorkflow(SequentialWorkflow):
    """在指定 Agent 执行前抛 WorkflowSuspended,模拟挂起。"""

    def __init__(self, suspend_agent_id: str) -> None:
        super().__init__(max_rewrites=0)
        self.suspend_agent_id = suspend_agent_id
        self.calls: list[str] = []

    def _run_agent_step(self, db, run_id, agent, ctx, *, sequence, name_suffix=""):
        self.calls.append(agent.agent_id)
        if agent.agent_id == self.suspend_agent_id:
            raise WorkflowSuspended(node=_NODE_BY_AGENT[agent.agent_id], reason="test")
        return super()._run_agent_step(
            db, run_id, agent, ctx, sequence=sequence, name_suffix=name_suffix
        )


def _make_fake_db(run: Run, task: Task) -> MagicMock:
    db = MagicMock()
    db.get.side_effect = lambda model, id_: run if model is Run else (task if model is Task else None)
    db.scalar.return_value = None

    def _fake_refresh(obj) -> None:
        pk = type(obj).__table__.primary_key.columns[0].key
        if getattr(obj, pk, None) is None:
            setattr(obj, pk, f"fake_{type(obj).__name__.lower()}")

    db.refresh.side_effect = _fake_refresh
    return db


@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_suspend_and_resume_skips_completed_steps(_mock) -> None:
    run = Run(id="run_s", task_id="task_s", input_snapshot={})
    task = Task(id="task_s", title="测试任务", description=None)
    db = _make_fake_db(run, task)

    wf = SuspendingWorkflow("agent_researcher")

    summary = wf.execute(db, "run_s")
    assert summary["suspended"] is True
    assert summary["node"] == "research"
    assert wf.calls == ["agent_planner", "agent_researcher"]
    assert run.metadata_ and "checkpoint" in run.metadata_

    # 清除挂起条件后恢复执行
    wf.suspend_agent_id = None
    result = wf.resume(db, "run_s")

    assert result["artifact_id"]
    assert result["quality"] in {"pass", "revision"}
    # planner 只执行一次(resume 跳过),researcher 执行两次(挂起前 + 恢复后)
    assert wf.calls.count("agent_planner") == 1
    assert wf.calls.count("agent_researcher") == 2
