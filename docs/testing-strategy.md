# Multi Agents 测试策略

## 1. 目标

Multi-agent 项目的测试不能只覆盖 API，还需要覆盖 workflow 行为、Agent 输出契约、Tool 权限、事件流和 Artifact 生成。

测试目标：

- 不依赖真实 LLM 也能验证核心逻辑。
- Workflow 可以稳定回归。
- Tool 调用安全边界可测试。
- SSE 事件顺序可靠。
- 失败、取消、重试和审批有覆盖。

## 2. 测试分层

```txt
Unit Tests
  -> Service Tests
  -> API Tests
  -> Workflow Tests
  -> Integration Tests
  -> E2E Tests
  -> Evaluation Tests
```

优先级：

- MVP：Unit、API、Workflow。
- Phase 2：LLM mock、Artifact snapshot。
- Phase 3：Tool permission、Approval。
- Phase 4：Parallel workflow。
- Phase 5：Evaluation。

## 3. 后端单元测试

覆盖：

- Pydantic schema。
- 状态机转换。
- event sequence 生成。
- retry policy。
- permission check。
- cost limit check。

示例用例：

```txt
run queued -> running 合法
run completed -> running 非法
step failed 后可以 retry
dangerous tool 必须 approval
```

## 4. API 测试

覆盖：

- 创建 task。
- 创建 run。
- 查询 run。
- 查询 events。
- 取消 run。
- 重试 run。
- 审批 run。
- 查询 artifact。

原则：

- 使用测试数据库。
- 不调用真实 worker 时，可以 mock job queue。
- 响应结构必须符合 API 文档。

## 5. Workflow 测试

Workflow 是核心测试对象。

覆盖：

- Sequential workflow 成功。
- Planner 输出非法 JSON。
- Writer 失败后重试。
- Reviewer 发现问题。
- Worker 接收到取消信号。
- 审批节点暂停和继续。
- 并行 worker 部分失败。

测试方式：

- 使用 fake Agent。
- 使用 fake LLM Provider。
- 使用内存或测试数据库 event store。
- 验证最终状态和事件序列。

断言重点：

```txt
run.status
step.status
event.type
event.sequence
artifact count
tool_call.status
```

## 6. LLM Mock

不要在常规测试中调用真实模型。

Mock Provider 应支持：

- 返回固定文本。
- 返回结构化 JSON。
- 返回非法 JSON。
- 模拟 timeout。
- 模拟 rate limit。
- 模拟工具调用。

这样可以稳定测试 Agent Runtime 的错误处理。

## 7. Tool 测试

覆盖：

- input schema 校验。
- output schema 校验。
- 权限检查。
- 审批检查。
- timeout。
- executor 异常。
- 敏感信息脱敏。

高风险工具必须测试：

- 未审批时不能执行。
- 审批拒绝后不能执行。
- 审批通过后只能执行原请求。

## 8. SSE 测试

覆盖：

- 初次订阅。
- 从 `after_sequence` 恢复。
- heartbeat。
- 断线重连。
- 事件顺序。
- run 完成后连接关闭策略。

断言：

- 不丢事件。
- 不重复处理已确认事件。
- sequence 单调递增。

## 9. 前端测试

MVP 覆盖：

- Dashboard 加载任务列表。
- 创建任务表单校验。
- Run detail 渲染不同状态。
- Timeline 增量追加事件。
- Artifact viewer 渲染 Markdown 和 JSON。
- 审批面板按钮状态。

建议：

- 组件测试覆盖复杂 UI。
- Playwright 覆盖端到端主流程。
- SSE 使用 mock server。

## 10. Artifact 快照测试

适合：

- Markdown 报告。
- JSON 结果。
- 代码生成结果。
- Prompt 模板输出。

注意：

- 快照只覆盖稳定结构。
- 时间、ID、随机内容需要归一化。
- 不要把大段模型自由文本作为脆弱快照。

## 11. Evaluation Tests

后期引入评估集：

```txt
input
expected_behavior
rubric
reference_output optional
```

指标：

- 任务完成度。
- 格式正确性。
- 事实准确性。
- 工具调用正确性。
- 成本。
- 耗时。

可以先人工评分，再逐步加入自动评分。

## 12. CI 策略

最小 CI：

```txt
backend tests
frontend lint
frontend tests
type checks
```

后续 CI：

```txt
database migration check
workflow regression
playwright e2e
security scan
docker build
```

## 13. 发布前检查

每次发布前至少确认：

- 核心 API 测试通过。
- Workflow 回归通过。
- 数据库 migration 可升级。
- 前端关键页面无明显错误。
- 取消、重试、审批路径可用。
- 运行事件可以回放。
