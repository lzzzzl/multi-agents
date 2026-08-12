# Multi Agents 工作台

一个「任务 → 多 Agent 协作 → 产出 Artifact」的全栈演示项目。基于 Next.js + FastAPI + PostgreSQL + Redis(RQ),内置一个顺序执行的 Agent Workflow(Planner → Researcher → Writer → Reviewer),支持实时事件流、Artifact 查看、工具调用以及运行控制的取消 / 重试 / 审批。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Next.js (App Router) · React · TypeScript · Tailwind CSS · TanStack Query |
| 后端 | FastAPI · SQLAlchemy · Alembic · Pydantic v2 |
| 基础设施 | PostgreSQL 16 · Redis 7 · RQ(worker) |
| 测试 | pytest(后端) · vitest + Testing Library(前端) |

## 目录结构

```txt
backend/     # FastAPI 服务、模型、API、Agent、Workflow、Tool、Worker
frontend/    # Next.js 工作台(任务 / 运行 / Artifact)
shared/      # 保留目录:未来跨包共享 schema
docs/        # 设计文档与实现计划
```

## 快速开始

> 依赖:docker、Python 3.12+、Node.js(LTS)。后端依赖已装于 `backend/.venv`。

**一键启动全部服务**(基础依赖 → 迁移 → 后端 API → worker → 前端):

```bash
./scripts/dev.sh up
```

启动后访问:

- 前端工作台:http://localhost:3000/tasks
- 后端 API 文档:http://localhost:8000/docs
- 健康检查:http://localhost:8000/health

**分步启动**(便于调试):

```bash
./scripts/dev.sh infra     # 启动 PostgreSQL + Redis(docker compose)
./scripts/dev.sh migrate   # 执行 Alembic 迁移
./scripts/dev.sh backend   # 启动 FastAPI(localhost:8000)
./scripts/dev.sh worker    # 启动 RQ worker(执行 workflow)
./scripts/dev.sh frontend  # 启动 Next.js(localhost:3000)
```

**其他命令:**

```bash
./scripts/dev.sh down      # 停止基础设施容器
./scripts/dev.sh test      # 运行后端 pytest + 前端 vitest
./scripts/dev.sh status    # 查看各服务进程是否在运行
```

## 手动启动(不依赖脚本)

```bash
# 1) 基础设施
docker compose up -d       # postgres:5433, redis:6380

# 2) 后端
cd backend
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000

# 3) worker(另开终端)
.venv/bin/rq worker runs

# 4) 前端(另开终端)
cd ../frontend
npm run dev
```

## 模型供应商

后端通过环境变量选择 LLM 供应商(`backend/.env`):

- `mock`:无需 API Key,本地兜底,用于自动化测试与演示。
- `deepseek` / `openai` / `dashscope` / `zhipu` / `ollama`:需配置 `LLM_API_KEY` 与 `LLM_BASE_URL`。

`backend/.env` 已被 `.gitignore` 忽略,不会提交密钥。

## 测试

```bash
cd backend && .venv/bin/python -m pytest   # 后端(全程 mock LLM,无需网络)
cd frontend && npm test                    # 前端 smoke test
```

## 文档

- 实现计划与进度:`docs/develop/implementation-plan.md`
- 架构:`docs/develop/technical-architecture.md`
- 数据模型:`docs/develop/data-model.md`
- API 设计:`docs/develop/api-design.md`