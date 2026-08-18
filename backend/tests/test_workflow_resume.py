"""挂起/恢复测试。"""

from unittest.mock import MagicMock, patch

from app.llms.mock import MockLLMProvider
from app.models import Run, Task, ToolCall
from app.tools.base import ApprovalRequired
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


class FakeApprovalRunner:
    """模拟 ToolRunner 的异步审批行为:获批前抛 ApprovalRequired,获批后返回完成记录。"""

    approved = False
    executions = 0  # 真正「执行」的次数(挂起不计)

    def __init__(self, db) -> None:
        self.db = db

    def run(self, *, run_id, tool_name, args, step_id=None, agent_id=None):
        if not FakeApprovalRunner.approved:
            # 模拟 ToolRunner:置 run 为 waiting_for_approval 并抛挂起信号
            run = self.db.get(Run, run_id)
            if run is not None:
                run.status = "waiting_for_approval"
            raise ApprovalRequired("tc_async", tool_name)
        FakeApprovalRunner.executions += 1
        return ToolCall(
            id="tc_async",
            run_id=run_id,
            tool_name=tool_name,
            status="completed",
            output={"sent": True, "_display": "[模拟通知] 已发送"},
        )


@patch("app.workflows.sequential.ToolRunner", FakeApprovalRunner)
@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_async_approval_suspend_then_resume(_mock) -> None:
    """Step 2.1 端到端:高风险工具触发挂起 -> 批准 -> resume 续跑,不重复执行。"""
    FakeApprovalRunner.approved = False
    FakeApprovalRunner.executions = 0

    run = Run(id="run_ap", task_id="task_ap", input_snapshot={})
    task = Task(id="task_ap", title="测试任务", description=None)
    db = _make_fake_db(run, task)

    wf = SuspendingWorkflow(None)  # 不在 Agent 步骤挂起,挂起只来自工具审批
    summary = wf.execute(db, "run_ap")

    # 1. execute 在 execute_tool 节点挂起:checkpoint 持久化、run 等待审批
    assert summary["suspended"] is True
    assert summary["node"] == "execute_tool"
    assert "审批" in summary["reason"]
    assert run.status == "waiting_for_approval"
    assert run.metadata_ and "checkpoint" in run.metadata_
    # plan/research 已完成,compose/finalize 未执行
    assert wf.calls == ["agent_planner", "agent_researcher"]
    assert FakeApprovalRunner.executions == 0

    # 2. 模拟审批通过(resume 入队后 worker 调用 workflow.resume)
    FakeApprovalRunner.approved = True
    run.status = "running"
    result = wf.resume(db, "run_ap")

    # 3. 续跑完成:工具只执行一次,已完成 Agent 不重复执行
    assert result["artifact_id"]
    assert FakeApprovalRunner.executions == 1
    assert wf.calls.count("agent_planner") == 1
    assert wf.calls.count("agent_researcher") == 1
    assert wf.calls.count("agent_writer") == 1
    assert wf.calls.count("agent_reviewer") == 1


@patch("app.workflows.sequential.ToolRunner", FakeApprovalRunner)
@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_async_approval_rejected_resume_continues(_mock) -> None:
    """拒绝路径:首次挂起,resume 时 ToolRunner 抛 ToolError,workflow 继续后续节点。"""
    from app.tools.base import ToolError

    class RejectingRunner(FakeApprovalRunner):
        resumed = False

        def run(self, *, run_id, tool_name, args, step_id=None, agent_id=None):
            if not RejectingRunner.resumed:
                # 首次:挂起等待审批
                RejectingRunner.resumed = True
                run = self.db.get(Run, run_id)
                if run is not None:
                    run.status = "waiting_for_approval"
                raise ApprovalRequired("tc_rej", tool_name)
            # resume:发现被拒,抛 ToolError 交回 workflow 处理
            raise ToolError("工具调用被人工拒绝", code="TOOL_REJECTED")

    run = Run(id="run_rj", task_id="task_rj", input_snapshot={})
    task = Task(id="task_rj", title="测试任务", description=None)
    db = _make_fake_db(run, task)

    with patch("app.workflows.sequential.ToolRunner", RejectingRunner):
        wf = SuspendingWorkflow(None)
        summary = wf.execute(db, "run_rj")
        assert summary["suspended"] is True
        result = wf.resume(db, "run_rj")  # 拒绝后续跑

    # 工具失败不中断 workflow:仍产出 artifact,compose/finalize 正常执行
    assert result["artifact_id"]
    assert wf.calls.count("agent_planner") == 1
    assert wf.calls.count("agent_writer") == 1
