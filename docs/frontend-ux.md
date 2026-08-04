# Multi Agents 前端产品与交互文档

## 1. 产品定位

前端应设计为 multi-agent 任务运行台，而不是单纯聊天框。用户需要看到任务是什么、哪些 Agent 正在工作、每一步做了什么、工具调用是否安全、最终结果在哪里。

核心体验：

- 创建任务足够快。
- 运行过程足够透明。
- 失败原因容易定位。
- 结果可以沉淀为 artifact。
- 高风险操作有明确审批。

## 2. 信息架构

建议页面：

```txt
/dashboard
/tasks/new
/tasks/[id]
/runs/[id]
/agents
/tools
/workflows
/artifacts/[id]
/settings
```

MVP 必做：

- `/dashboard`
- `/tasks/new`
- `/runs/[id]`
- `/artifacts/[id]`

## 3. Dashboard

目标：让用户快速看到当前任务状态。

内容：

- 最近任务列表。
- 正在运行的 runs。
- 最近失败的 runs。
- 成本和耗时摘要。
- 快速创建任务入口。

任务列表字段：

```txt
title
status
latest_run_status
created_at
updated_at
duration
artifact_count
```

交互：

- 点击任务进入 task detail。
- 点击运行进入 run detail。
- 支持按状态筛选。

## 4. 创建任务页

目标：让用户提交目标和约束。

表单字段：

- 任务标题。
- 任务描述。
- 输出格式。
- 语言。
- Workflow 模板。
- 约束条件。

高级选项：

- 模型偏好。
- 最大成本。
- 是否允许工具调用。
- 是否需要审批所有外部写操作。

提交流程：

```txt
POST /api/tasks
  -> POST /api/runs
  -> navigate to /runs/{run_id}
```

## 5. Run Detail

这是最重要页面。

建议布局：

```txt
Header: task title / run status / controls

Left: step and agent list
Center: timeline
Right: details panel
Bottom: user input and approval actions
```

Header 内容：

- Run 状态。
- Workflow 名称。
- 耗时。
- 费用估算。
- 取消、重试按钮。

左侧：

- Step 列表。
- Agent 状态。
- 当前执行节点。
- 失败节点高亮。

中间：

- Run events timeline。
- Agent message。
- Tool call event。
- LLM call summary。
- Artifact created event。

右侧：

- 当前选中事件详情。
- Tool 参数和结果。
- LLM 调用摘要。
- Step 输入输出。
- 错误堆栈摘要。

底部：

- 需要用户补充信息时显示输入框。
- 需要审批时显示审批操作。

## 6. Timeline 事件展示

事件展示原则：

- 默认展示摘要。
- 复杂 payload 折叠。
- 错误事件醒目但不遮挡其他内容。
- 支持按 Agent、Step、事件类型过滤。

事件类型展示：

```txt
run_started: 运行开始
agent_message: Agent 输出
tool_call_started: 工具调用开始
tool_call_completed: 工具调用完成
human_approval_required: 等待审批
artifact_created: 结果已生成
run_completed: 运行完成
run_failed: 运行失败
```

## 7. Artifact Viewer

支持类型：

- Markdown。
- JSON。
- Text。
- HTML。
- Image。
- File download。

MVP：

- Markdown preview。
- JSON viewer。
- 原始内容查看。

后续：

- Diff。
- 评论。
- 导出。
- 版本对比。

## 8. Agents 页面

目标：管理 Agent 配置。

内容：

- Agent 列表。
- 角色描述。
- 模型配置。
- Prompt 配置。
- 输入输出 schema。
- 允许调用的工具。

交互：

- 新建 Agent。
- 编辑 Agent。
- 禁用 Agent。
- 测试 Agent。

MVP 可以先只读展示内置 Agent。

## 9. Tools 页面

目标：管理工具和权限。

内容：

- Tool 列表。
- 风险等级。
- 是否需要审批。
- 输入输出 schema。
- 最近调用记录。

交互：

- 启用或禁用工具。
- 修改审批策略。
- 查看调用历史。

## 10. Workflows 页面

MVP 可以只展示 workflow 列表。

后续 Workflow Studio 支持：

- 可视化节点图。
- 节点配置。
- Tool 权限配置。
- 条件分支。
- dry run。
- 发布版本。

## 11. 状态与反馈

运行状态：

```txt
queued
running
waiting_for_approval
completed
failed
cancelled
```

交互反馈：

- queued：显示排队状态。
- running：持续接收 SSE。
- waiting_for_approval：突出审批面板。
- completed：展示 artifact。
- failed：展示失败 step 和错误。
- cancelled：保留历史事件。

## 12. 前端状态管理

建议：

- 服务器状态使用 TanStack Query。
- SSE 增量事件进入本地 run event store。
- 页面刷新后从 API 重建状态。
- Zustand 只存 UI 状态，例如选中的事件和展开面板。

## 13. MVP 页面优先级

优先级：

```txt
/dashboard
  -> /tasks/new
  -> /runs/[id]
  -> /artifacts/[id]
  -> /agents
  -> /tools
  -> /workflows
```

验收标准：

- 用户能创建任务并进入运行详情页。
- 用户能实时看到事件流。
- 用户能查看最终 artifact。
- 用户能取消失败或长期运行的 run。
