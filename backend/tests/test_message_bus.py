"""Step 3.2 消息总线测试。

覆盖:
- publish/latest/history 基本语义(多消息保留历史、latest 取最新);
- to_state/from_state 状态往返(checkpoint 持久化);
- 深拷贝隔离:发布后修改原 dict 不影响总线内消息;
- workflow 端到端:上游 Agent 输出经 bus 传递到下游 prompt(见 test_workflow.py)。
"""

from app.agents.message_bus import MessageBus


def test_publish_and_latest() -> None:
    bus = MessageBus()
    bus.publish("agent_planner", {"steps": [1]})
    bus.publish("agent_planner", {"steps": [1, 2]})

    assert bus.latest("agent_planner") == {"steps": [1, 2]}
    assert bus.latest("agent_reviewer") is None  # 未发布主题


def test_history_preserves_order() -> None:
    bus = MessageBus()
    bus.publish("agent_writer", {"markdown": "v1"})
    bus.publish("agent_writer", {"markdown": "v2"})
    bus.publish("agent_writer", {"markdown": "v3"})

    history = bus.history("agent_writer")
    assert [m["markdown"] for m in history] == ["v1", "v2", "v3"]
    # Writer 重写场景:最新一条即上一稿
    assert bus.latest("agent_writer")["markdown"] == "v3"


def test_history_empty_topic_returns_empty_list() -> None:
    bus = MessageBus()
    assert bus.history("unknown") == []


def test_state_roundtrip() -> None:
    bus = MessageBus()
    bus.publish("agent_planner", {"steps": []})
    bus.publish("agent_writer", {"markdown": "v1"})
    bus.publish("agent_writer", {"markdown": "v2"})

    state = bus.to_state()
    restored = MessageBus.from_state(state)

    assert restored.latest("agent_planner") == {"steps": []}
    assert [m["markdown"] for m in restored.history("agent_writer")] == ["v1", "v2"]
    # 恢复后可继续发布
    restored.publish("agent_writer", {"markdown": "v3"})
    assert len(restored.history("agent_writer")) == 3


def test_from_state_none_or_empty() -> None:
    assert MessageBus.from_state(None).topics() == []
    assert MessageBus.from_state({}).topics() == []


def test_messages_are_deep_copied() -> None:
    bus = MessageBus()
    msg = {"steps": [{"name": "a"}]}
    bus.publish("agent_planner", msg)
    msg["steps"].append({"name": "b"})  # 修改原对象不应影响总线

    assert bus.latest("agent_planner") == {"steps": [{"name": "a"}]}

    got = bus.latest("agent_planner")
    got["steps"].append({"name": "c"})  # 修改读取结果不影响总线
    assert len(bus.latest("agent_planner")["steps"]) == 1


def test_topics_lists_published_only() -> None:
    bus = MessageBus()
    bus.publish("agent_planner", {})
    bus.publish("tool_result", {})
    assert bus.topics() == ["agent_planner", "tool_result"]
