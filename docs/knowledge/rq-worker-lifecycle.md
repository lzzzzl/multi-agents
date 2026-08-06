# 知识文档：RQ 队列与 Worker 生命周期

> 对应代码：`backend/app/workers/queue.py`、`backend/app/workers/run_worker.py`

## 1. 为什么要把长任务放进 Worker

Agent workflow 是耗时操作（多次 LLM 调用），不能阻塞 HTTP 请求。职责划分：

- **API**：创建 Task / Run，投递后台 job，立即返回。
- **Worker**：消费队列，加载 run，执行真实 workflow，持续写事件。

## 2. 选择的队列：RQ

项目最终选择 **RQ**（Redis Queue），配置在 `queue.py`：

```python
from redis import Redis
from rq import Queue
from app.core.config import settings

_redis = Redis.from_url(settings.REDIS_URL, decode_responses=False)
runs_queue = Queue("runs", connection=_redis)

def get_queue() -> Queue:
    return runs_queue
```

启动 worker：

```bash
cd backend
uv run rq worker runs
```

> ⚠️ **文档与实现不一致提示**：`development-guide.md` 里仍并列写了 RQ 和 Celery 两套启动命令，实际已定用 RQ。建议后续更新 `development-guide.md`，删掉 Celery 分支，避免维护歧义。

## 3. Worker 的执行入口：`execute_run(run_id)`

由 RQ 调用，整体流程：

```python
def execute_run(run_id: str) -> None:
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if not run:
            logger.error(...); return
        if run.status == "cancelled":
            logger.info("already cancelled, skip"); return

        # 1. 标记 running
        run.status = "running"
        run.started_at = _now()
        db.commit()

        # 2. 执行真实 workflow
        workflow = SequentialWorkflow()
        try:
            summary = workflow.execute(db, run_id)
            if summary.get("cancelled"):
                return
            _append_event(db, run_id, type="run_completed",
                          payload={"artifact_id": summary["artifact_id"]})
            run.status = "completed"
            run.completed_at = _now()
            run.output_summary = {...}
            run.cost_summary = {...}
            db.commit()
        except Exception as exc:
            logger.exception(...)
            run.status = "failed"
            run.failed_at = _now()
            run.error_message = str(exc)
            db.commit()
            _append_event(db, run_id, type="run_failed",
                          payload={"error": str(exc)})
    finally:
        db.close()
```

## 4. Run 状态机

```txt
queued -> running -> completed
                  \-> failed
queued -> cancelled（跳过执行）
```

- 创建 run 时由 API 置为 `queued` 并投递 job。
- Worker 开始时置 `running`。
- 成功后置 `completed` 并写 `run_completed` 事件。
- 异常时置 `failed`、记 `error_message`、写 `run_failed` 事件。
- 已取消的 run 直接跳过（不执行）。

## 5. Worker 记录了什么

- `run.started_at / completed_at / failed_at`：时间点。
- `run.output_summary`：`{artifact_id, steps}`。
- `run.cost_summary`：`{input_tokens, output_tokens, estimated_cost}`。
- `run.error_message`：失败原因。
- 事件由 workflow 内部写入（step/agent/artifact），worker 只补 `run_completed` / `run_failed`。

## 6. 已知取舍

- **`_append_event` 在 worker 和 workflow 里各有一份**：事件 sequence 计算逻辑重复。可抽成 `EventService` 统一管理。
- **单 worker / 单队列**：`WORKER_CONCURRENCY` 当前未在 worker 侧真正生效到并发执行，后续可加多 worker 水平扩展。
- **取消只保证 step 边界**：worker 靠 workflow 内部的 `_check_cancelled` 在 step 边界感知取消，不中断进行中的 LLM 调用。

## 7. 排查建议

run 卡住或失败时，按这个顺序看：

1. `runs.status` —— 总状态。
2. `run_steps` —— 卡在哪个 step。
3. `run_events` —— sequence 到哪了。
4. worker 日志 —— 异常栈（`logger.exception` 会打印）。

## 8. 后续改进

- 把 `_append_event` 收敛到 service，避免跨模块重复。
- 支持从失败 step 重试（当前重试方式是新建 run）。
- 接入取消/审批控制信号（当前只有取消检查）。