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

- [ ] 定义 artifact 类型。
- [ ] 支持 Markdown artifact。
- [ ] 支持 JSON artifact。
- [ ] 后端实现 artifact 查询接口。
- [ ] 前端实现 artifact viewer。
- [ ] 运行完成后自动创建 artifact。

验收：

- Run 完成后能看到最终 artifact。
- Artifact 可以被独立打开和查看。

## 12. Step 10: Tool 系统

目标：让 Agent 能安全调用工具。

任务清单：

- [ ] 实现 `Tool` model。
- [ ] 实现 `ToolCall` model。
- [ ] 实现 Tool Registry。
- [ ] 定义 Tool 输入输出 schema。
- [ ] 实现第一个 safe tool。
- [ ] 实现工具调用事件。
- [ ] 前端展示 tool call 参数和结果。

验收：

- Agent 可以调用已注册工具。
- Tool 调用过程可审计。
- Tool 失败时 run 能记录错误。

## 13. Step 11: 取消、重试和审批

目标：增强运行控制能力。

任务清单：

- [ ] 实现 `POST /api/runs/{run_id}/cancel`。
- [ ] 实现 `POST /api/runs/{run_id}/retry`。
- [ ] 实现 `POST /api/runs/{run_id}/approve`。
- [ ] Worker 支持检查取消信号。
- [ ] 失败 step 支持重试。
- [ ] 高风险工具调用支持人工审批。
- [ ] 前端展示审批面板。

验收：

- 用户可以取消运行。
- 失败运行可以重试。
- 需要审批的工具调用会暂停等待。

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
