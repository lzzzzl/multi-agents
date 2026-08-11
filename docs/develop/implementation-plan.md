# Multi Agents 具体执行文档

## 1. 使用方式

本文档用于把项目从零一步步落地。建议开发时按阶段推进，每完成一个任务就在对应条目旁标记完成，并补充关键实现决策。

## 2. Step 0: 初始化仓库结构

目标：建立清晰的 monorepo 基础目录。

任务清单：

- [ ] 创建 `backend/` 目录。
- [ ] 创建 `frontend/` 目录。
- [ ] 创建 `shared/` 目录。
- [ ] 创建 `docs/` 目录。
- [ ] 创建根目录 `.env.example`。
- [ ] 创建根目录 `README.md`。
- [ ] 创建根目录 `docker-compose.yml`。
- [ ] 明确 Python、Node.js、PostgreSQL、Redis 版本。

建议结构：

```txt
backend/
frontend/
shared/
docs/
```

验收：

- 根目录结构清晰。
- 文档、后端、前端、共享 schema 各自独立。

## 3. Step 1: 后端工程初始化

目标：启动一个可运行的 FastAPI 服务。

任务清单：

- [ ] 初始化 Python 项目。
- [ ] 安装 FastAPI、Uvicorn、Pydantic Settings。
- [ ] 创建 `backend/app/main.py`。
- [ ] 创建 `/health` 健康检查接口。
- [ ] 创建配置模块 `core/config.py`。
- [ ] 创建日志模块 `core/logging.py`。
- [ ] 创建测试目录 `backend/tests/`。
- [ ] 添加后端启动命令。

建议依赖：

```txt
fastapi
uvicorn
pydantic-settings
sqlalchemy
alembic
psycopg
redis
rq 或 celery
pytest
httpx
```

验收：

- 运行后端服务后，`GET /health` 返回正常状态。
- 配置可以从环境变量读取。

## 4. Step 2: 前端工程初始化

目标：启动一个可运行的 Next.js 应用。

任务清单：

- [ ] 初始化 Next.js App Router 项目。
- [ ] 启用 TypeScript。
- [ ] 配置 Tailwind CSS。
- [ ] 安装 shadcn/ui。
- [ ] 安装 TanStack Query。
- [ ] 创建基础布局。
- [ ] 创建 `/dashboard` 页面。
- [ ] 创建 API client。

建议依赖：

```txt
next
react
typescript
tailwindcss
@tanstack/react-query
lucide-react
shadcn/ui
```

验收：

- 前端可以正常启动。
- `/dashboard` 页面可以访问。
- API client 可以调用后端 `/health`。

## 5. Step 3: 本地基础设施

目标：用 Docker Compose 启动 PostgreSQL 和 Redis。

任务清单：

- [ ] 配置 PostgreSQL 服务。
- [ ] 配置 Redis 服务。
- [ ] 配置数据库连接环境变量。
- [ ] 配置 Redis 连接环境变量。
- [ ] 补充 `.env.example`。
- [ ] 验证后端可以连接 PostgreSQL。
- [ ] 验证后端可以连接 Redis。

建议环境变量：

```txt
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/multi_agents
REDIS_URL=redis://localhost:6379/0
APP_ENV=local
```

验收：

- `docker compose up` 可以启动数据库和 Redis。
- 后端启动时能正常连接基础设施。

## 6. Step 4: 数据库模型与迁移

目标：实现核心数据表。

任务清单：

- [ ] 配置 SQLAlchemy。
- [ ] 配置 Alembic。
- [ ] 实现 `Task` model。
- [ ] 实现 `Run` model。
- [ ] 实现 `RunStep` model。
- [ ] 实现 `RunEvent` model。
- [ ] 实现 `Artifact` model。
- [ ] 创建第一版 migration。
- [ ] 编写基础 repository 或 service。

最小模型：

```txt
tasks
runs
run_steps
run_events
artifacts
```

验收：

- 可以执行 migration。
- 可以通过测试创建并查询 `Task` 和 `Run`。

## 7. Step 5: Task 和 Run API

目标：实现最小可用任务 API。

任务清单：

- [ ] `POST /api/tasks` 创建任务。
- [ ] `GET /api/tasks` 查询任务列表。
- [ ] `GET /api/tasks/{task_id}` 查询任务详情。
- [ ] `POST /api/runs` 创建运行。
- [ ] `GET /api/runs/{run_id}` 查询运行详情。
- [ ] `GET /api/runs/{run_id}/events` 查询事件列表。
- [ ] 补充 API 测试。

验收：

- 前端或 curl 可以创建任务。
- 创建任务后可以创建 run。
- 查询 run 时可以看到状态和事件。

## 8. Step 6: Worker 和模拟运行

目标：让长任务离开 HTTP 请求，在后台执行。

任务清单：

- [ ] 选择 RQ、Celery 或 Dramatiq。
- [ ] 创建 worker 配置。
- [ ] 创建 `run_worker.py`。
- [ ] API 创建 run 后投递后台 job。
- [ ] Worker 加载 run。
- [ ] Worker 写入 `run_started` 事件。
- [ ] Worker 模拟写入若干 step 事件。
- [ ] Worker 写入 `run_completed` 事件。
- [ ] 支持失败时写入 `run_failed`。

验收：

- 用户创建 run 后 HTTP 请求很快返回。
- Worker 能异步执行 run。
- 数据库中能看到事件持续增加。

## 9. Step 7: SSE 实时事件流

目标：前端能实时看到运行事件。

任务清单：

- [ ] 实现 `GET /api/runs/{run_id}/events/stream`。
- [ ] 支持 `Last-Event-ID` 或游标。
- [ ] Worker 写事件后能推送给订阅者。
- [ ] 前端实现 `useRunEvents`。
- [ ] 运行详情页展示 timeline。
- [ ] 处理断线重连。

验收：

- 运行过程中前端无需刷新即可看到新事件。
- 页面刷新后能从历史事件恢复状态。

## 10. Step 8: 第一个 Agent Workflow

目标：接入真实 Agent 执行链路。

任务清单：

- [ ] 实现 LLM Provider 抽象。
- [ ] 实现模型调用配置。
- [ ] 实现 `BaseAgent`。
- [ ] 实现 `PlannerAgent`。
- [ ] 实现 `WriterAgent`。
- [ ] 实现 `ReviewerAgent`。
- [ ] 实现 sequential workflow。
- [ ] 每个 Agent 执行时写入事件。
- [ ] 记录 LLM 调用摘要。

验收：

- 用户输入一个目标后，系统能生成结构化计划。
- 系统能生成最终 Markdown 输出。
- Agent 执行过程在前端可见。

## 11. Step 9: Artifact 管理

目标：把最终结果独立保存和展示。

任务清单：

- [x] 定义 artifact 类型。
- [x] 支持 Markdown artifact。
- [x] 支持 JSON artifact。
- [x] 后端实现 artifact 查询接口。
- [x] 前端实现 artifact viewer。
- [x] 运行完成后自动创建 artifact。

验收：

- Run 完成后能看到最终 artifact。
- Artifact 可以被独立打开和查看。

关键实现决策：

- 后端在 `SequentialWorkflow.execute` 收尾阶段生成两种 artifact:Markdown 报告(`{task.title}.md`)与执行摘要 JSON(`execution-summary.json`,含计划/质量/重写轮次/成本);均写入 `artifacts` 表并触发 `artifact_created` 事件。content 内联存储,便于独立查看与下载。
- 查询接口:`GET /api/runs/{run_id}/artifacts` 列表、`GET /api/artifacts/{artifact_id}` 单条详情(`backend/app/api/artifacts.py`,schema `backend/app/schemas/artifact.py`)。
- 前端新增可复用 `ArtifactViewer`(`frontend/components/ArtifactViewer.tsx`),按 `type` 渲染:markdown 用 react-markdown 富文本,json 用等宽语法块,其余纯文本。
- 运行详情页 `frontend/app/runs/[id]/page.tsx` 增加产物区块:多 artifact 切换(报告/摘要按钮)、`新窗口打开`链接。
- 新增独立查看页 `frontend/app/artifacts/[id]/page.tsx`:展示元信息(MIME/大小/时间/产出 Agent)、ArtifactViewer 渲染、下载按钮(基于内联 content 生成 Blob)。
- 真实 DeepSeek 调用时,Reviewer 的 `final_content` 常含未转义换行导致 JSON 解析失败;增强 `backend/app/agents/_json.py` 的 `load_json`,在解析失败时把字符串值内的裸换行/回车转义为 `\n` 后再解析。

## 12. Step 10: Tool 系统

目标：让 Agent 能安全调用工具。

任务清单：

- [x] 实现 `Tool` model。
- [x] 实现 `ToolCall` model。
- [x] 实现 Tool Registry。
- [x] 定义 Tool 输入输出 schema。
- [x] 实现第一个 safe tool。
- [x] 实现工具调用事件。
- [x] 前端展示 tool call 参数和结果。

验收：

- Agent 可以调用已注册工具。
- Tool 调用过程可审计。
- Tool 失败时 run 能记录错误。

关键实现决策：

- Tool 由代码注册(`app/tools/registry.py` 单例 + `builtin.py`),不落 DB 表;每次调用落一条 `tool_calls` 记录(`app/models/tool_call.py`,含 input/output/status/risk_level/duration,迁移 `bf4a7ce789b8`)。`Tool` 抽象基类(`app/tools/base.py`)定义 name/description/risk_level/input_schema 与 execute,`ToolResult` 携带结构化 output 与展示用 display。
- `ToolRunner`(`app/tools/runner.py`)统一执行:创建 `ToolCall`(running)→写 `tool_call_started` 事件→执行→完成/失败回写记录并写 `tool_call_completed`/`tool_call_failed` 事件;工具产出 `display` 存入 `output["_display"]` 供前端展示。
- 内置 safe 工具:`current_time`、`generate_report`(本地确定性初稿,无外部依赖)。
- 新增 `ResearcherAgent`(`app/agents/researcher.py`):声明 `tool_use`(generate_report),由 workflow 经 ToolRunner 执行并注入 `previous["tool_result"]`,`WriterAgent` 读取 `tool_result.draft` 作为撰写素材。工具未声明/失败时不中断 workflow(兜底 generate_report)。
- 查询接口:`GET /api/runs/{run_id}/tool_calls`(`app/api/runs.py`)返回 Toolkit 列表。
- 前端运行详情页(`frontend/app/runs/[id]/page.tsx`)新增“工具调用”区块,展示 id/工具名/状态/耗时/输入参数/错误;`RunTimeline` 支持 `tool_call_started/completed/failed` 事件标签。
- 单元测试:`tests/test_workflow.py` 新增 `test_workflow_executes_tool_call`,验证 Researcher 触发工具、ToolCall 记录完整且 output 含 `_display`;同步更新步骤计数断言(新增 Researcher 步骤)。

## 13. Step 11: 取消、重试和审批

目标：增强运行控制能力。

任务清单：

- [x] 实现 `POST /api/runs/{run_id}/cancel`。
- [x] 实现 `POST /api/runs/{run_id}/retry`。
- [x] 实现 `POST /api/runs/{run_id}/approve`。
- [x] Worker 支持检查取消信号。
- [x] 失败 step 支持重试。
- [x] 高风险工具调用支持人工审批。
- [x] 前端展示审批面板。

验收：

- 用户可以取消运行。
- 失败运行可以重试。
- 需要审批的工具调用会暂停等待。

关键实现决策：

- 取消:已有 `POST /api/runs/{id}/cancel`(`RunService.cancel`),workflow 各步骤边界通过 `_check_cancelled` 检查取消信号,优先后续步骤不再执行。
- 重试:`POST /api/runs/{id}/retry`(`RunService.retry`),仅允许 failed/cancelled 状态;以源 run 的输入快照与 workflow 创建新 run(记录 `source_run_id`)并入队。
- 审批:`POST /api/runs/{id}/approve`,body `{decision: "approve"|"reject"}`(`RunService.approve` / schema `RunApprove`)。仅允许 `waiting_for_approval` 状态,把对应 ToolCall 与 run 转目标状态并写 `tool_call_approved/rejected` 事件。
- 高风险工具审批:`ToolRunner` 对 `risk_level != safe` 的工具先进入审批——创建 `waiting_for_approval` ToolCall、置 run 为 `waiting_for_approval`、写 `tool_call_waiting_for_approval` 事件,然后阻塞轮询(默认 300s 超时)审批结果;获批后转为 running 执行,被拒抛 `TOOL_REJECTED`,取消抛 `RUN_CANCELLED`。内置敏感工具 `send_notification`(模拟,不真正发送)用于演示审批。
- 前端:运行详情页 `frontend/app/runs/[id]/page.tsx` 增加审批面板(waiting_for_approval 时显示批准/拒绝)与重试按钮(failed/cancelled 时);`RunTimeline` 支持 `tool_call_waiting_for_approval/approved/rejected/cancelled` 事件标签。
- 测试:`tests/test_approval.py` 新增敏感工具审批(批准执行/拒绝报错)与重试(新建 run 携带 source、拒绝运行中 run)共 4 用例;端到端脚本验证批准-执行、拒绝-记录、重试-新建三条链路。

## 14. Step 12: 测试与质量

目标：建立最小可靠测试体系。

任务清单：

- [ ] 后端 API 测试。
- [ ] 数据模型测试。
- [ ] Worker 测试。
- [ ] Workflow 测试。
- [ ] Tool mock 测试。
- [ ] LLM mock 测试。
- [ ] 前端关键页面 smoke test。

验收：

- 核心路径有自动化测试。
- 不依赖真实 LLM 也能跑通 workflow 测试。

## 15. 开发顺序建议

推荐顺序：

```txt
后端健康检查
  -> 数据库迁移
  -> Task / Run API
  -> Worker 模拟运行
  -> SSE
  -> 前端运行详情页
  -> Agent Runtime
  -> Artifact
  -> Tool
  -> 取消 / 重试 / 审批
```

这个顺序能让项目很早就拥有一条端到端链路，后续每加一个 Agent 或 Tool 都可以直接在运行台里验证。
