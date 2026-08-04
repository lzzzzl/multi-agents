# Multi Agents 本地开发指南

## 1. 目标

本文档用于说明项目本地开发环境、启动方式、环境变量、数据库迁移、测试和常见问题。实际脚手架创建后，应持续更新本文件中的命令。

## 2. 推荐环境

建议版本：

```txt
Python 3.12+
Node.js 20+
PostgreSQL 16+
Redis 7+
```

推荐工具：

```txt
uv 或 poetry
pnpm
Docker Desktop
```

## 3. 目录结构

建议：

```txt
backend/
  app/
  tests/

frontend/
  app/
  components/
  lib/

shared/
  schemas/
  prompts/

docs/
```

## 4. 环境变量

根目录 `.env.example` 建议包含：

```txt
APP_ENV=local
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/multi_agents
REDIS_URL=redis://localhost:6379/0
BACKEND_CORS_ORIGINS=http://localhost:3000

LLM_PROVIDER=openai
OPENAI_API_KEY=
DEFAULT_MODEL=gpt-5

WORKER_CONCURRENCY=2
RUN_MAX_STEPS=30
RUN_MAX_COST_USD=2.00
```

原则：

- `.env` 不提交。
- `.env.example` 保留变量名和安全默认值。
- 生产密钥使用部署平台 secret 管理。

## 5. Docker Compose

本地基础设施：

```txt
postgres
redis
```

建议命令：

```bash
docker compose up -d
docker compose ps
docker compose logs -f postgres
docker compose logs -f redis
```

## 6. 后端启动

建议命令，实际以项目脚手架为准：

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

健康检查：

```bash
curl http://localhost:8000/api/health
```

## 7. 前端启动

建议命令：

```bash
cd frontend
pnpm install
pnpm dev
```

默认地址：

```txt
http://localhost:3000
```

## 8. Worker 启动

如果使用 RQ：

```bash
cd backend
uv run rq worker runs
```

如果使用 Celery：

```bash
cd backend
uv run celery -A app.workers.celery_app worker --loglevel=info
```

最终选择一种后，应删除另一种命令，避免维护歧义。

## 9. 数据库迁移

建议命令：

```bash
cd backend
uv run alembic revision --autogenerate -m "create core tables"
uv run alembic upgrade head
uv run alembic downgrade -1
```

规则：

- 每次模型变更必须生成 migration。
- migration 文件需要 code review。
- 不在应用启动时自动修改 schema。

## 10. 后端测试

建议命令：

```bash
cd backend
uv run pytest
```

常用测试：

```bash
uv run pytest tests/api
uv run pytest tests/workflows
uv run pytest tests/tools
```

测试原则：

- API 测试不调用真实 LLM。
- Workflow 测试使用 mock provider。
- Tool 测试默认使用 fake executor。

## 11. 前端测试

建议命令：

```bash
cd frontend
pnpm lint
pnpm test
pnpm e2e
```

MVP 至少覆盖：

- Dashboard 渲染。
- 创建任务表单。
- Run detail 事件流展示。
- Artifact viewer。

## 12. 常见开发流程

新增 API：

```txt
定义 schema
  -> 实现 service
  -> 实现 router
  -> 添加测试
  -> 前端 API client 接入
```

新增 Agent：

```txt
定义 input/output schema
  -> 实现 Agent class
  -> 添加 mock provider 测试
  -> 加入 workflow
  -> 前端展示事件
```

新增 Tool：

```txt
定义 input/output schema
  -> 实现 executor
  -> 注册 Tool
  -> 配置权限和审批
  -> 添加 ToolCall 记录
  -> 添加测试
```

## 13. 调试建议

排查 run：

- 先看 `runs.status`。
- 再看 `run_steps`。
- 再看 `run_events`。
- 最后看 `llm_calls` 和 `tool_calls`。

排查前端实时问题：

- 检查 SSE 连接是否建立。
- 检查 `after_sequence`。
- 检查后端是否持续写入 events。
- 检查浏览器是否重连。

## 14. 提交前检查

建议：

```bash
cd backend
uv run pytest

cd frontend
pnpm lint
pnpm test
```

未来可以在根目录增加统一命令：

```bash
make test
make lint
make dev
```
