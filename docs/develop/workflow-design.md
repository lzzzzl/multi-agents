# Multi Agents Workflow 编排设计

## 1. 目标

Workflow 负责把一个用户目标拆成可执行步骤，并协调多个 Agent、Tool、人工审批和 Artifact 生成。

设计目标：

- 支持简单顺序执行，也支持复杂图编排。
- 每个步骤状态清晰。
- 支持重试、取消、暂停、恢复。
- 支持人工审批。
- 支持版本化和历史回放。

## 2. 核心概念

```txt
WorkflowDefinition
WorkflowVersion
WorkflowRun
WorkflowNode
WorkflowEdge
WorkflowState
WorkflowContext
```

和数据库模型的对应关系：

```txt
WorkflowRun -> runs
WorkflowNode execution -> run_steps
Workflow event -> run_events
```

## 3. Workflow Definition

Workflow 定义建议包含：

```json
{
  "name": "sequential_report",
  "version": "1.0.0",
  "nodes": [],
  "edges": [],
  "input_schema": {},
  "output_schema": {},
  "retry_policy": {},
  "metadata": {}
}
```

节点类型：

```txt
agent
tool
condition
approval
parallel
join
artifact
system
```

边类型：

```txt
default
success
failure
condition
timeout
approval_granted
approval_rejected
```

## 4. Sequential Workflow

最适合 MVP。

```txt
Planner -> Writer -> Reviewer
```

特点：

- 实现简单。
- 容易调试。
- 对状态管理要求低。
- 适合报告生成、摘要、基础分析任务。

执行规则：

- 前一个 step completed 后执行下一个。
- 任一 step failed 时 run failed。
- 支持从失败 step 重试。

## 5. Planner Executor Workflow

适合动态任务拆解。

```txt
Planner -> Executor Step 1 -> Executor Step 2 -> Reviewer
```

特点：

- Planner 输出结构化 plan。
- Orchestrator 根据 plan 创建 run_steps。
- Executor 按 step 执行。

注意事项：

- Planner 输出必须有 schema。
- 动态 step 数量必须有限制。
- 每个 step 需要最大重试次数。
- 不允许 Planner 无限生成新任务。

## 6. Supervisor Worker Workflow

适合多 Agent 并行。

```txt
Supervisor
  -> Worker A
  -> Worker B
  -> Worker C
  -> Synthesizer
  -> Reviewer
```

特点：

- Supervisor 拆任务。
- Worker 并行执行。
- Synthesizer 汇总结果。
- Reviewer 做质量检查。

适用场景：

- 竞品调研。
- 代码库分析。
- 多资料源总结。
- 多方案生成和比较。

## 7. Graph Workflow

适合条件分支、循环、审批、错误恢复。

```txt
Start -> Plan -> Execute -> Check
                    |        |
                    v        v
                  Retry    Approval
```

需要支持：

- 节点状态机。
- 条件表达式。
- 并行 join。
- 最大循环次数。
- 超时控制。
- 版本化。

第一版可以只实现内部图结构，不急着做前端编辑器。

## 8. Human In The Loop

人工审批是 workflow 的一等节点。

触发场景：

- 高风险 Tool 调用。
- Agent 输出低置信度。
- 成本超过阈值。
- 需要用户补充信息。
- 外部写操作。

审批状态：

```txt
pending
approved
rejected
expired
cancelled
```

执行规则：

- 进入审批节点时 run 状态变为 `waiting_for_approval`。
- 审批通过后继续。
- 审批拒绝后按 workflow 定义失败、跳过或走替代分支。

## 9. 状态机

Run 状态：

```txt
queued
running
waiting_for_approval
completed
failed
cancelled
```

Step 状态：

```txt
pending
running
waiting_for_approval
completed
failed
skipped
cancelled
```

状态变化原则：

- 状态变化必须写入 `run_events`。
- Worker 只负责推进合法状态。
- API 控制操作通过命令或信号影响 Worker。
- 历史状态不可覆盖，只能追加事件。

## 10. 取消与恢复

取消策略：

- API 写入 cancel signal。
- Worker 在 step 边界检查。
- 可中断工具需要主动终止。
- 不可中断工具完成后不再进入下一步。

恢复策略：

- 从历史 run_events 重建状态。
- 从未完成 step 继续。
- 或创建新 run 并带上 source_run_id。

MVP 建议：

- 取消只保证 step 边界生效。
- 重试默认创建新 run。

## 11. 版本管理

Workflow 必须版本化。

原因：

- 历史 run 需要可回放。
- 新 workflow 不应改变旧运行解释。
- 评估需要比较不同版本质量。

建议字段：

```txt
workflow_name
workflow_version
definition_snapshot
```

每次 run 开始时保存 workflow definition snapshot。

## 12. Workflow Studio

后续可视化编辑器建议支持：

- 节点拖拽。
- 边连接。
- 节点配置面板。
- 输入输出 schema 编辑。
- Tool 权限选择。
- 条件分支配置。
- dry run。
- 版本保存和发布。

运行详情页应该展示实际执行路径，而不是只展示静态定义。

## 13. MVP 实现顺序

推荐顺序：

```txt
SequentialWorkflow
  -> PlannerExecutorWorkflow
  -> SupervisorWorkerWorkflow
  -> GraphWorkflow
  -> Workflow Studio
```

第一版只要把 step、event、artifact 记录打稳，后续扩展图编排会顺很多。
