# Multi Agents 技术架构文档

## 1. 项目定位

本项目目标是构建一个基于 Python 后端和 Next.js 前端的 multi-agent 工作台。系统应支持用户创建任务、编排多个 Agent 协作执行、实时观察运行过程、保存历史记录，并在失败时支持排查、重试和恢复。

核心设计原则：

- Agent 协作过程可观察、可回放、可审计。
- Workflow 先确定性、后智能化，避免过早依赖完全自治 Agent。
- Agent 输出尽量结构化，降低后续编排、校验和调试成本。
- Tool 调用必须有权限边界，高风险操作需要人工审批。
- API 层、编排层、运行时、工具系统、持久化层保持清晰边界。

## 2. 总体架构

```txt
Next.js Frontend
  |
  | REST / SSE / WebSocket
  v
FastAPI Backend
  |
  | create run / stream events / control task
  v
Workflow Orchestrator
  |
  | dispatch steps
  v
Agent Runtime + Tool Runtime
  |
  | background jobs
  v
Workers / Queue / Model Providers / External Tools
  |
  v
PostgreSQL / Redis / Vector DB / Object Storage
```

推荐第一阶段使用：

- 后端：FastAPI、Pydantic、SQLAlchemy、Alembic
- 数据库：PostgreSQL
- 队列与缓存：Redis
- 后台任务：RQ、Celery 或 Dramatiq
- 前端：Next.js App Router、TypeScript、Tailwind CSS、shadcn/ui
- 实时通信：SSE 优先，复杂双向协作再引入 WebSocket

## 3. 后端技术框架

FastAPI 只负责 API、鉴权、请求校验和运行控制，不直接执行耗时 Agent 任务。Agent 执行应放入后台 worker。

建议模块结构：

```txt
backend/
  app/
    main.py

    api/
      tasks.py
      runs.py
      agents.py
      tools.py
      events.py

    core/
      config.py
      security.py
      logging.py

    db/
      session.py
      base.py
      migrations/

    models/
      user.py
      agent.py
      task.py
      run.py
      event.py
      tool.py
      artifact.py

    schemas/
      agent.py
      task.py
      run.py
      event.py
      tool.py

    agents/
      base.py
      planner.py
      executor.py
      reviewer.py
      supervisor.py

    workflows/
      base.py
      sequential.py
      supervisor.py
      graph.py

    tools/
      base.py
      web_search.py
      file_reader.py
      code_runner.py
      database_query.py

    llms/
      base.py
      openai_provider.py
      anthropic_provider.py
      local_provider.py

    workers/
      celery_app.py
      run_worker.py

    services/
      task_service.py
      run_service.py
      event_service.py
      artifact_service.py
```

核心后端职责：

- `api/`：暴露 REST、SSE、任务控制接口。
- `services/`：封装业务用例，例如创建任务、启动运行、取消运行。
- `workflows/`：定义 Agent 协作流程。
- `agents/`：定义不同 Agent 的角色、输入输出和执行逻辑。
- `tools/`：定义 Agent 可调用工具及其权限边界。
- `llms/`：封装模型供应商，避免业务层直接依赖某个模型 SDK。
- `workers/`：执行长任务，并持续写入运行事件。

## 4. 前端技术框架

前端不建议只做聊天框，而是做成任务运行台。

推荐技术栈：

- Next.js App Router
- TypeScript
- Tailwind CSS
- shadcn/ui
- TanStack Query
- Zustand 可选，用于本地 UI 状态
- SSE，用于运行日志和 Agent 输出流
- React Flow 可选，用于展示 Workflow 图
- Monaco Editor 可选，用于查看 JSON、Prompt、代码和工具参数

建议页面：

```txt
frontend/
  app/
    dashboard/
    tasks/new/
    runs/[id]/
    agents/
    tools/
    artifacts/[id]/
    settings/

  components/
    run-timeline/
    agent-panel/
    tool-call-viewer/
    artifact-viewer/
    workflow-graph/

  lib/
    api.ts
    sse.ts
    query.ts

  hooks/
    use-run-events.ts
    use-run-control.ts

  types/
    agent.ts
    task.ts
    run.ts
    event.ts
    tool.ts
```

`runs/[id]` 是最关键页面，建议布局：

```txt
左侧：任务、Agent、Step 列表
中间：运行 Timeline 和实时事件流
右侧：当前输出、工具调用、调试信息
底部：用户输入、审批、继续执行
```

## 5. 核心领域模型

建议从以下核心对象开始：

- `Agent`：一个可执行角色，包含 prompt、模型配置、工具权限、输入输出约束。
- `Task`：用户提交的目标。
- `Run`：一次任务执行记录。
- `RunStep`：一次运行中的具体步骤。
- `RunEvent`：运行过程中的事件流，用于实时展示和历史回放。
- `Message`：Agent、用户和系统之间的消息。
- `Tool`：Agent 可调用的能力定义。
- `ToolCall`：一次具体工具调用记录。
- `Artifact`：运行产生的文件、报告、JSON、图片或其他结果。

数据库表建议：

```txt
users
agents
tools
tasks
runs
run_steps
run_events
messages
tool_calls
artifacts
```

其中 `run_events` 是调试和可观测性的核心表。每一步运行状态、Agent 输出、工具调用和错误都应该写入事件流。

## 6. Agent 模型

Agent 不应只是一个 prompt，而应该是一个有明确契约的执行单元。

建议结构：

```txt
Agent =
  name
  role
  system_prompt
  model_config
  allowed_tools
  memory_policy
  input_schema
  output_schema
```

示例 Agent：

- `PlannerAgent`：将用户目标拆解成结构化计划。
- `ResearcherAgent`：执行资料收集和信息提炼。
- `WriterAgent`：根据中间结果生成报告或最终输出。
- `ReviewerAgent`：检查结果质量、完整性和风险。
- `SupervisorAgent`：分配任务、收敛多 Agent 输出、处理异常分支。

Planner 输出应尽量结构化，例如：

```json
{
  "steps": [
    {
      "id": "step_1",
      "agent": "researcher",
      "goal": "Collect competitor information",
      "depends_on": []
    },
    {
      "id": "step_2",
      "agent": "writer",
      "goal": "Generate final report",
      "depends_on": ["step_1"]
    }
  ]
}
```

## 7. Workflow 编排

第一阶段建议支持三类 workflow。

### 7.1 Sequential Workflow

适合 MVP 和确定性任务。

```txt
Planner -> Researcher -> Writer -> Reviewer
```

优点是简单、稳定、容易调试。

### 7.2 Supervisor Workflow

适合多个 Worker 并行处理子任务。

```txt
Supervisor
  -> Worker A
  -> Worker B
  -> Worker C
  -> Synthesizer
```

优点是扩展性强，适合调研、代码分析、文档生成等任务。

### 7.3 Graph Workflow

适合复杂状态机和条件分支。

```txt
Node A -> Node B -> Node C
          |         |
          v         v
        Retry     Human Approval
```

可以参考 LangGraph 的状态机思想，但建议核心领域模型和运行记录自己掌控，避免过早被框架锁死。

## 8. 任务执行流程

标准执行链路：

```txt
用户提交任务
  -> FastAPI 创建 Task
  -> FastAPI 创建 Run
  -> 投递后台 job
  -> Worker 加载 Run 和 Workflow
  -> Worker 执行 Agent Step
  -> Worker 调用 LLM / Tool
  -> Worker 写入 RunEvent
  -> 前端通过 SSE 订阅事件
  -> Run 完成后生成 Artifact
```

任务控制接口：

```txt
POST /api/tasks
GET  /api/tasks
GET  /api/tasks/{task_id}

POST /api/runs
GET  /api/runs/{run_id}
GET  /api/runs/{run_id}/events
GET  /api/runs/{run_id}/events/stream
POST /api/runs/{run_id}/cancel
POST /api/runs/{run_id}/retry
POST /api/runs/{run_id}/approve

GET  /api/agents
POST /api/agents
GET  /api/tools
GET  /api/artifacts/{artifact_id}
```

## 9. 实时事件设计

SSE 事件建议统一使用 `RunEvent`。

事件类型：

```txt
run_started
run_completed
run_failed
run_cancelled

step_started
step_completed
step_failed
step_retried

agent_started
agent_message
agent_completed

llm_call_started
llm_call_completed
llm_call_failed

tool_call_started
tool_call_completed
tool_call_failed

human_approval_required
artifact_created
```

事件 payload 示例：

```json
{
  "id": "evt_123",
  "run_id": "run_123",
  "type": "tool_call_completed",
  "timestamp": "2026-08-04T12:00:00Z",
  "agent_id": "agent_researcher",
  "step_id": "step_1",
  "payload": {
    "tool_name": "web_search",
    "duration_ms": 1200,
    "summary": "Collected 5 relevant sources"
  }
}
```

## 10. Tool 系统

Tool 是 Agent 能力边界，必须有明确 schema、权限和执行约束。

建议结构：

```txt
Tool =
  name
  description
  input_schema
  output_schema
  permission_scope
  timeout_seconds
  requires_approval
  executor
```

工具风险等级：

- `safe`：低风险，无需审批，例如读取公开资料。
- `sensitive`：涉及私有数据，需要用户确认。
- `dangerous`：可能产生外部影响，必须审批，例如写文件、发邮件、部署、付款。

第一阶段建议只实现：

- `web_search`
- `read_document`
- `generate_report`
- `query_vector_store`

后续再加入：

- `write_file`
- `run_code`
- `http_request`
- `send_email`
- `create_github_issue`
- `deploy_app`

## 11. 记忆与检索

不建议第一版就构建复杂长期记忆。建议分三层：

- `Run Memory`：当前任务上下文，来自 messages、steps、events。
- `Project Memory`：项目文档、历史运行结果、知识库。
- `Long-term Memory`：用户偏好、组织知识、长期经验。

存储建议：

- PostgreSQL：结构化业务数据。
- pgvector：MVP 阶段的向量检索。
- Qdrant 或 Weaviate：后续更专业的向量数据库。
- S3 或 MinIO：存储报告、图片、文件等 artifact。

## 12. 可观测性

Multi-agent 系统必须把调试能力作为一等公民。

至少记录：

- 每次 LLM 调用的模型名、输入、输出、token、耗时和费用估算。
- 每次 Tool 调用的参数、结果、耗时和错误。
- 每个 Agent Step 的状态转换。
- 每次重试、取消、审批和失败原因。
- 最终 artifact 与其生成来源。

推荐后续接入：

- OpenTelemetry
- Sentry
- Prometheus + Grafana
- LangSmith 或 Phoenix

## 13. 权限与安全

建议从第一版就建立基础权限模型。

基础对象：

```txt
User
Team
Project
Agent
Tool
Permission
```

需要重点控制：

- 用户是否能查看某个 task 或 run。
- Agent 是否能调用某个 tool。
- Tool 是否可以访问某类数据源。
- 高风险工具调用是否需要人工审批。
- 代码执行是否需要沙箱隔离。
- 外部写操作是否有审计记录。

## 14. MVP 范围

第一版建议目标：

```txt
后端：
FastAPI + PostgreSQL + Redis + RQ/Celery

前端：
Next.js + TypeScript + Tailwind CSS + shadcn/ui + SSE

Agent：
Planner
Researcher
Writer
Reviewer

Workflow：
Planner -> Researcher -> Writer -> Reviewer

功能：
创建任务
实时运行日志
任务历史
Agent 配置
工具调用记录
最终 Markdown 报告
失败重试
取消任务
```

暂不建议第一版实现：

- 完全自治 Agent 群聊。
- 复杂 Agent 市场。
- 完整插件系统。
- 复杂多租户权限。
- 过度复杂长期记忆。
- 高风险外部写操作自动执行。

## 15. 迭代路线

### Phase 1: 基础工作台

- 搭建 FastAPI、Next.js、PostgreSQL、Redis。
- 实现 Task、Run、RunEvent、Artifact。
- 实现固定顺序 workflow。
- 实现 SSE 实时事件流。
- 实现基础任务列表和运行详情页。

### Phase 2: Agent 与 Tool 抽象

- 实现 Agent 配置管理。
- 实现 Tool schema 和工具权限。
- 记录 LLM 调用和 Tool 调用。
- 支持失败重试和取消运行。
- 加入 Markdown artifact 查看。

### Phase 3: Supervisor 与并行协作

- 实现 Supervisor Workflow。
- 支持多个 Worker Agent 并行执行。
- 支持 Synthesizer 汇总结果。
- 引入 React Flow 展示 workflow 图。

### Phase 4: 记忆、检索和评估

- 引入 pgvector。
- 支持项目知识库。
- 建立运行质量评估指标。
- 引入成本、耗时、成功率统计。

### Phase 5: 生产化能力

- 接入 OpenTelemetry、Sentry。
- 增强权限和审批系统。
- 支持沙箱化代码执行。
- 支持更多外部工具和模型供应商。
- 支持团队协作和多项目管理。
