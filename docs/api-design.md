# Multi Agents API 设计

## 1. 设计目标

API 需要支持前端工作台的核心流程：

- 创建任务。
- 启动运行。
- 查询任务和运行状态。
- 实时订阅运行事件。
- 控制运行取消、重试、审批。
- 查看 Agent、Tool 和 Artifact。

第一版 API 以 REST + SSE 为主。WebSocket 留给后续多人协作或复杂双向实时控制。

## 2. 通用约定

基础路径：

```txt
/api
```

响应格式：

```json
{
  "data": {},
  "error": null
}
```

错误格式：

```json
{
  "data": null,
  "error": {
    "code": "RUN_NOT_FOUND",
    "message": "Run not found",
    "details": {}
  }
}
```

分页参数：

```txt
limit
cursor
```

时间格式：

```txt
ISO 8601
```

ID 建议：

```txt
task_...
run_...
step_...
evt_...
agent_...
tool_...
artifact_...
```

## 3. Health

### GET /api/health

检查后端服务状态。

响应：

```json
{
  "data": {
    "status": "ok"
  },
  "error": null
}
```

## 4. Tasks

### POST /api/tasks

创建任务。

请求：

```json
{
  "title": "生成竞品分析报告",
  "description": "分析三个竞品的定位、功能、价格和差异化机会",
  "input": {
    "output_format": "markdown",
    "constraints": ["中文输出", "包含表格"]
  }
}
```

响应：

```json
{
  "data": {
    "id": "task_123",
    "title": "生成竞品分析报告",
    "description": "分析三个竞品的定位、功能、价格和差异化机会",
    "status": "draft",
    "created_at": "2026-08-04T12:00:00Z"
  },
  "error": null
}
```

### GET /api/tasks

查询任务列表。

查询参数：

```txt
status 可选
limit 可选
cursor 可选
```

响应：

```json
{
  "data": {
    "items": [
      {
        "id": "task_123",
        "title": "生成竞品分析报告",
        "status": "completed",
        "latest_run_id": "run_123",
        "created_at": "2026-08-04T12:00:00Z",
        "updated_at": "2026-08-04T12:05:00Z"
      }
    ],
    "next_cursor": null
  },
  "error": null
}
```

### GET /api/tasks/{task_id}

查询任务详情。

响应：

```json
{
  "data": {
    "id": "task_123",
    "title": "生成竞品分析报告",
    "description": "分析三个竞品的定位、功能、价格和差异化机会",
    "status": "completed",
    "input": {
      "output_format": "markdown"
    },
    "runs": [
      {
        "id": "run_123",
        "status": "completed",
        "created_at": "2026-08-04T12:00:00Z"
      }
    ]
  },
  "error": null
}
```

## 5. Runs

### POST /api/runs

为任务创建一次运行。

请求：

```json
{
  "task_id": "task_123",
  "workflow_name": "sequential_report",
  "input_override": {}
}
```

响应：

```json
{
  "data": {
    "id": "run_123",
    "task_id": "task_123",
    "workflow_name": "sequential_report",
    "status": "queued",
    "created_at": "2026-08-04T12:00:00Z"
  },
  "error": null
}
```

说明：

- API 创建 run 后应投递后台 job。
- 不应在 HTTP 请求内直接执行 Agent workflow。

### GET /api/runs/{run_id}

查询运行详情。

响应：

```json
{
  "data": {
    "id": "run_123",
    "task_id": "task_123",
    "workflow_name": "sequential_report",
    "status": "running",
    "started_at": "2026-08-04T12:00:05Z",
    "completed_at": null,
    "steps": [
      {
        "id": "step_1",
        "name": "Planner",
        "type": "agent",
        "status": "completed",
        "agent_id": "agent_planner"
      },
      {
        "id": "step_2",
        "name": "Writer",
        "type": "agent",
        "status": "running",
        "agent_id": "agent_writer"
      }
    ],
    "cost_summary": {
      "input_tokens": 1200,
      "output_tokens": 800,
      "estimated_cost": 0.02
    }
  },
  "error": null
}
```

### GET /api/runs/{run_id}/events

查询运行事件列表。

查询参数：

```txt
after_sequence 可选
limit 可选
```

响应：

```json
{
  "data": {
    "items": [
      {
        "id": "evt_123",
        "run_id": "run_123",
        "sequence": 1,
        "type": "run_started",
        "payload": {},
        "created_at": "2026-08-04T12:00:05Z"
      }
    ],
    "next_sequence": 2
  },
  "error": null
}
```

### GET /api/runs/{run_id}/events/stream

SSE 订阅运行事件。

查询参数：

```txt
after_sequence 可选
```

事件格式：

```txt
id: 12
event: run_event
data: {"id":"evt_123","sequence":12,"type":"agent_message","payload":{"content":"..."}}
```

建议：

- SSE `id` 使用 `run_events.sequence`。
- 前端断线重连时带上最后收到的 sequence。
- 后端应定期发送 heartbeat，避免连接被中间层关闭。

### POST /api/runs/{run_id}/cancel

取消运行。

请求：

```json
{
  "reason": "用户手动取消"
}
```

响应：

```json
{
  "data": {
    "id": "run_123",
    "status": "cancelled"
  },
  "error": null
}
```

说明：

- 如果 run 已完成，返回当前状态即可。
- Worker 需要周期性检查取消信号。

### POST /api/runs/{run_id}/retry

重试运行。

请求：

```json
{
  "mode": "from_failed_step"
}
```

可选模式：

```txt
from_start
from_failed_step
```

响应：

```json
{
  "data": {
    "id": "run_124",
    "source_run_id": "run_123",
    "status": "queued"
  },
  "error": null
}
```

建议：

- 默认创建新的 run，而不是覆盖旧 run。
- 保留 `source_run_id` 方便追溯。

### POST /api/runs/{run_id}/approve

审批等待中的操作。

请求：

```json
{
  "approval_id": "approval_123",
  "decision": "approved",
  "comment": "允许读取该文档"
}
```

响应：

```json
{
  "data": {
    "approval_id": "approval_123",
    "status": "approved",
    "run_id": "run_123"
  },
  "error": null
}
```

## 6. Agents

### GET /api/agents

查询 Agent 列表。

响应：

```json
{
  "data": {
    "items": [
      {
        "id": "agent_planner",
        "name": "planner",
        "display_name": "Planner",
        "role": "任务规划",
        "status": "active"
      }
    ]
  },
  "error": null
}
```

### POST /api/agents

创建 Agent 配置。

请求：

```json
{
  "name": "planner",
  "display_name": "Planner",
  "role": "任务规划",
  "description": "将用户目标拆解为结构化步骤",
  "system_prompt": "You are a planning agent.",
  "model_provider": "openai",
  "model_name": "gpt-5",
  "model_config": {
    "temperature": 0.2
  },
  "input_schema": {},
  "output_schema": {}
}
```

响应：

```json
{
  "data": {
    "id": "agent_planner",
    "name": "planner",
    "status": "active"
  },
  "error": null
}
```

## 7. Tools

### GET /api/tools

查询工具列表。

响应：

```json
{
  "data": {
    "items": [
      {
        "id": "tool_generate_report",
        "name": "generate_report",
        "display_name": "Generate Report",
        "risk_level": "safe",
        "requires_approval": false,
        "status": "active"
      }
    ]
  },
  "error": null
}
```

### GET /api/tools/{tool_id}

查询工具详情。

响应：

```json
{
  "data": {
    "id": "tool_generate_report",
    "name": "generate_report",
    "description": "Generate a Markdown report from structured inputs.",
    "risk_level": "safe",
    "input_schema": {},
    "output_schema": {},
    "timeout_seconds": 60,
    "requires_approval": false
  },
  "error": null
}
```

## 8. Tool Calls

### GET /api/runs/{run_id}/tool-calls

查询某次运行的工具调用记录。

响应：

```json
{
  "data": {
    "items": [
      {
        "id": "tool_call_123",
        "run_id": "run_123",
        "tool_id": "tool_generate_report",
        "status": "completed",
        "duration_ms": 1300,
        "created_at": "2026-08-04T12:00:20Z"
      }
    ]
  },
  "error": null
}
```

## 9. Artifacts

### GET /api/runs/{run_id}/artifacts

查询某次运行生成的结果。

响应：

```json
{
  "data": {
    "items": [
      {
        "id": "artifact_123",
        "run_id": "run_123",
        "type": "markdown",
        "name": "竞品分析报告.md",
        "mime_type": "text/markdown",
        "created_at": "2026-08-04T12:05:00Z"
      }
    ]
  },
  "error": null
}
```

### GET /api/artifacts/{artifact_id}

查询 artifact 内容。

响应：

```json
{
  "data": {
    "id": "artifact_123",
    "type": "markdown",
    "name": "竞品分析报告.md",
    "mime_type": "text/markdown",
    "content": "# 竞品分析报告\n\n...",
    "storage_url": null
  },
  "error": null
}
```

## 10. 前端调用顺序

创建并运行任务：

```txt
POST /api/tasks
  -> POST /api/runs
  -> 跳转 /runs/{run_id}
  -> GET /api/runs/{run_id}
  -> GET /api/runs/{run_id}/events
  -> GET /api/runs/{run_id}/events/stream
```

运行详情页刷新：

```txt
GET /api/runs/{run_id}
  -> GET /api/runs/{run_id}/events
  -> GET /api/runs/{run_id}/artifacts
  -> 建立 SSE 连接
```

审批流程：

```txt
SSE 收到 human_approval_required
  -> 前端展示审批面板
  -> POST /api/runs/{run_id}/approve
  -> SSE 继续接收后续事件
```

## 11. 错误码建议

```txt
TASK_NOT_FOUND
RUN_NOT_FOUND
RUN_ALREADY_COMPLETED
RUN_NOT_CANCELLABLE
RUN_NOT_RETRYABLE
AGENT_NOT_FOUND
TOOL_NOT_FOUND
TOOL_PERMISSION_DENIED
APPROVAL_NOT_FOUND
APPROVAL_ALREADY_RESOLVED
ARTIFACT_NOT_FOUND
VALIDATION_ERROR
INTERNAL_ERROR
```

## 12. MVP API 范围

第一阶段必须实现：

```txt
GET  /api/health
POST /api/tasks
GET  /api/tasks
GET  /api/tasks/{task_id}
POST /api/runs
GET  /api/runs/{run_id}
GET  /api/runs/{run_id}/events
GET  /api/runs/{run_id}/events/stream
POST /api/runs/{run_id}/cancel
GET  /api/runs/{run_id}/artifacts
GET  /api/artifacts/{artifact_id}
```

第二阶段实现：

```txt
GET  /api/agents
POST /api/agents
GET  /api/tools
GET  /api/tools/{tool_id}
GET  /api/runs/{run_id}/tool-calls
POST /api/runs/{run_id}/retry
POST /api/runs/{run_id}/approve
```
