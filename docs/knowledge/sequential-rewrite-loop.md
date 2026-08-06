# 知识文档：SequentialWorkflow 的 Writer→Reviewer 重写循环

> 对应代码：`backend/app/workflows/sequential.py`
> 配套测试：`backend/tests/test_workflow.py`

## 1. 流程总览

`SequentialWorkflow`（`name = "sequential_report"`，`version = "1.1.0"`）编排三个 Agent：

```txt
Planner
  -> (Writer -> Reviewer)*  直到 quality == "pass" 或达到最大重写轮次
  -> 生成 Markdown Artifact
```

不是简单的"走一遍就完"，而是引入**自动重写循环**：Writer 出稿后由 Reviewer 评审，若 `quality == "revision"`，把评审反馈连同上一稿回传给 Writer 重写，循环直到通过或达到上限。

## 2. 两个关键控制量

- `WORKFLOW_MAX_REWRITES`（`config.py`，默认 `3`）：**不含首次出稿**的最大重写轮次。
- 构造时可用 `max_rewrites` 覆盖配置值（测试里用 `SequentialWorkflow(max_rewrites=0/2)` 精确控制）。

首轮 Writer 出稿后每轮都由 **Writer + Reviewer 一对**组成。所以总步数 = `1 (Planner) + 2 * (1 + rewrites)`，重写轮次用 `steps // 2 - 1` 反推。

## 3. 每个 Agent 步骤做什么

`_run_agent_step` 统一负责一个 Agent 的执行与记录：

1. 创建 `RunStep`（agent_id、name、type=agent、status=running、sequence、started_at）。
2. 写 `step_started` 事件。
3. 调 `agent.run(ctx)` 得到 `AgentResult`。
4. 标记 step completed，把 `output`、token/model/latency 写入 `step.metadata_`。
5. 写 `agent_message` 事件（含 `content` / `agent` / `output`）。
6. 写 `step_completed` 事件。

```python
step.metadata_ = {
    "input_tokens": result.usage.input_tokens,
    "output_tokens": result.usage.output_tokens,
    "model": result.usage.model,
    "latency_ms": result.latency_ms,
}
```

## 4. 重写循环的判定与内容回退

核心逻辑：

```python
quality = "revision"
for round_no in range(self._max_rewrites + 1):
    if self._check_cancelled(db, run_id):
        return {"cancelled": True}
    suffix = "" if round_no == 0 else f"·修改{round_no}"

    writer_result = self._run_agent_step(...)     # Writer 出稿/重写
    reviewer_result = self._run_agent_step(...)   # Reviewer 评审

    quality = reviewer_result.output.get("quality") or "revision"
    final_content = (
        reviewer_result.output.get("final_content")
        or writer_result.output.get("markdown")
        or writer_result.output.get("content")
        or ""
    )
    if quality == "pass":
        break
    if round_no >= self._max_rewrites:
        break   # 达到上限，即使 revision 也停
```

**`final_content` 的回退链**（重要）：优先 Reviewer 的 `final_content`（定稿），否则取 Writer 的 `markdown`，再否则 `content`。因为 Reviewer 可能修正过内容，定稿以评审为准。

## 5. 上下文如何传递

`_make_context` 构造 `AgentContext`，通过 `previous` 字典在轮次间传递各自的输出：

- `previous["agent_planner"]`：计划，喂给 Writer。
- `previous["agent_writer"]`：上一篇稿子，喂给 Reviewer 和重写时的 Writer。
- `previous["agent_reviewer"]`：评审意见，喂给重写时的 Writer（`writer.py` 据此带上"上一稿评审意见"和"上一稿内容"）。

Writer 重写时（见 `writer.py`）若 review 的 `quality == "revision"`，会把 feedback 和上一稿拼进 user prompt，要求"保留有价值内容，针对意见修改后重新输出完整正文"。

## 6. 取消检查

在每个 step 边界用 `_check_cancelled` 检查 run 是否已取消（`run.status == "cancelled"`），命中则返回 `{"cancelled": True}`，由 worker 跳过收尾。**只保证 step 边界生效**，不做运行中强行中断。

## 7. 事件序列的生成

`_append_event` 用数据库聚合计算下一次 `sequence`：

```python
current_max = db.scalar(select(func.max(RunEvent.sequence)).where(RunEvent.run_id == run_id))
next_seq = (current_max or 0) + 1
```

保证单 run 内 `sequence` 单调递增，前端 SSE 拿它当游标。

## 8. 成本估算

`_estimate_cost` 用固定单价做简化估算（元）：

```python
return round(input_tokens / 1_000_000 * 0.5 + output_tokens / 1_000_000 * 2.0, 4)
```

注意：不同模型价格不同，这只是占位估算，后续应接入按模型定价。

## 9. 测试要点（`test_workflow.py`）

用 `MagicMock` 伪造 session + `MockLLMProvider`，不依赖数据库：

- `max_rewrites=2` → 预期 5 步、`rewrites == 1`、`quality == "pass"`、有 artifact_id。
- `max_rewrites=0` → 首次评审即 revision 且不允许重写 → 3 步、`rewrites == 0`、`quality == "revision"`、仍有 artifact_id。

伪造 db 需要 mock `get`、`scalar`（返回值 None 作为 sequence 基线）、`refresh`（为无主键对象补 `fake_xxx` 主键）。

## 10. 已知取舍与改进方向

- **达到上限后仍以 revision 收尾并生成 artifact**：当前不抛错，只是 warning。可考虑"未达标"时标记 run 为 failed 或加人工审批。
- **`previous` 只存最近一轮**：`agent_writer` / `agent_reviewer` 会被覆盖，历史轮次的稿子不可见。如需审计完整修订历史，应把每轮存档。
- **`_append_event` 的 sequence 用聚合查询**：并发写会有竞态，当前单 worker 场景可接受，多 worker 需加唯一约束或改用序列。