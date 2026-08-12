#!/usr/bin/env bash
# Multi Agents 本地开发启动脚本。
# 用法: ./scripts/dev.sh <command>
# 命令: up | infra | migrate | backend | worker | frontend | down | test | status | help
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV_PY="$BACKEND/.venv/bin/python"
VENV_UVICORN="$BACKEND/.venv/bin/uvicorn"
VENV_RQ="$BACKEND/.venv/bin/rq"

C_GREEN=$'\033[32m'; C_RED=$'\033[31m'; C_YELLOW=$'\033[33m'; C_RESET=$'\033[0m'

info()  { printf '%s[info]%s %s\n' "$C_GREEN" "$C_RESET" "$1"; }
warn()  { printf '%s[warn]%s %s\n' "$C_YELLOW" "$C_RESET" "$1"; }
err()   { printf '%s[error]%s %s\n' "$C_RED" "$C_RESET" "$1" >&2; }

require_py() {
  if [[ ! -x "$VENV_PY" ]]; then
    err "未找到后端虚拟环境: $VENV_PY"
    err "请先在 backend/ 下创建并安装依赖,例如: python3 -m venv backend/.venv && backend/.venv/bin/pip install -e 'backend[dev]'"
    exit 1
  fi
}

cmd_infra() {
  info "启动 PostgreSQL + Redis (docker compose)"
  (cd "$ROOT" && docker compose up -d)
  info "基础设施已启动: postgres=localhost:5433, redis=localhost:6380"
}

cmd_migrate() {
  require_py
  info "执行 Alembic 迁移"
  (cd "$BACKEND" && "$VENV_PY" -m alembic upgrade head)
  info "迁移完成"
}

cmd_backend() {
  require_py
  info "启动后端 API: http://localhost:8000/docs"
  (cd "$BACKEND" && "$VENV_UVICORN" app.main:app --reload --port 8000)
}

cmd_worker() {
  require_py
  info "启动 RQ worker(队列: runs)"
  (cd "$BACKEND" && "$VENV_RQ" worker runs)
}

cmd_frontend() {
  info "启动前端: http://localhost:3000/tasks"
  (cd "$FRONTEND" && npm run dev)
}

cmd_down() {
  info "停止基础设施容器"
  (cd "$ROOT" && docker compose down)
}

cmd_test() {
  require_py
  info "运行后端测试"
  (cd "$BACKEND" && "$VENV_PY" -m pytest -q)
  info "运行前端测试"
  (cd "$FRONTEND" && npm test)
  info "前端类型检查"
  (cd "$FRONTEND" && npx tsc --noEmit)
}

cmd_status() {
  info "检查基础设施容器"
  (cd "$ROOT" && docker compose ps)
  info "检查后端进程 (uvicorn :8000)"
  pgrep -fl "uvicorn.*app.main" || warn "后端未运行"
  info "检查 worker 进程 (rq worker)"
  pgrep -fl "rq worker" || warn "worker 未运行"
  info "检查前端进程 (next dev :3000)"
  pgrep -fl "next dev" || warn "前端未运行"
}

cmd_up() {
  cmd_infra
  cmd_migrate
  info "依次启动 backend / worker / frontend(请分终端观察日志)"
  cmd_backend
  cmd_worker
  cmd_frontend
}

usage() {
  sed -n '2,4p' "$0"
  printf '\n命令:\n'
  printf '  up        一键启动: infra -> migrate -> backend + worker + frontend\n'
  printf '  infra     仅启动 PostgreSQL + Redis\n'
  printf '  migrate   执行 Alembic 迁移\n'
  printf '  backend   启动 FastAPI (localhost:8000)\n'
  printf '  worker    启动 RQ worker (队列 runs)\n'
  printf '  frontend  启动 Next.js (localhost:3000)\n'
  printf '  down      停止基础设施容器\n'
  printf '  test      运行后端 + 前端测试并做类型检查\n'
  printf '  status    查看各服务运行状态\n'
}

CMD="${1:-help}"
case "$CMD" in
  up)      cmd_up ;;
  infra)   cmd_infra ;;
  migrate) cmd_migrate ;;
  backend) cmd_backend ;;
  worker)  cmd_worker ;;
  frontend) cmd_frontend ;;
  down)    cmd_down ;;
  test)    cmd_test ;;
  status)  cmd_status ;;
  help|-h|--help) usage ;;
  *)
    err "未知命令: $CMD"
    usage
    exit 2
    ;;
esac