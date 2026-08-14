"""WorkflowCheckpoint 序列化测试。"""

from app.workflows.checkpoint import WorkflowCheckpoint


def test_checkpoint_roundtrip() -> None:
    checkpoint = WorkflowCheckpoint(
        workflow_name="sequential_report",
        completed_nodes=["plan", "research"],
        context={
            "previous": {"agent_planner": {"steps": []}},
            "stats": {"sequence": 2, "input_tokens": 10, "output_tokens": 20, "steps": 2},
            "cancelled": False,
            "quality": "revision",
            "rewrites": 0,
            "final_content": "",
        },
        suspended_node="execute_tool",
        reason="approval",
    )
    restored = WorkflowCheckpoint.from_dict(checkpoint.to_dict())
    assert restored == checkpoint
