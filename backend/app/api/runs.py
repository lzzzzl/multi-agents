"""Run 相关路由,含 SSE 事件流。"""

import json

from fastapi import APIRouter, Depends, Query
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.schemas.common import ApiResponse
from app.schemas.run import RunCreate, RunDetailOut, RunEventOut, RunEventPage, RunOut, RunStepOut
from app.services import EventService, RunService

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=ApiResponse[RunOut])
def create_run(payload: RunCreate, db: Session = Depends(get_db)) -> ApiResponse:
    run = RunService(db).create(payload)
    return ApiResponse.ok(RunOut.model_validate(run))


@router.get("/{run_id}", response_model=ApiResponse[RunDetailOut])
def get_run(run_id: str, db: Session = Depends(get_db)) -> ApiResponse:
    run = RunService(db).get_detail(run_id)
    steps = [RunStepOut.model_validate(s) for s in run.steps]
    detail = RunDetailOut(**RunOut.model_validate(run).model_dump(), steps=steps)
    return ApiResponse.ok(detail)


@router.get("/{run_id}/events", response_model=ApiResponse[RunEventPage])
def list_events(
    run_id: str,
    after_sequence: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> ApiResponse:
    events = EventService(db).list(run_id, after_sequence=after_sequence, limit=limit)
    items = [RunEventOut.model_validate(e) for e in events]
    next_seq = items[-1].sequence if items else after_sequence
    return ApiResponse.ok(RunEventPage(items=items, next_sequence=next_seq))


@router.get("/{run_id}/events/stream")
async def stream_events(
    run_id: str,
    after_sequence: int | None = None,
) -> EventSourceResponse:
    """SSE 订阅运行事件。断线重连时带 Last-Event-ID / after_sequence。"""

    async def event_generator():
        # 每个连接使用独立会话,避免与请求生命周期耦合
        db = SessionLocal()
        try:
            service = EventService(db)
            async for ev in service.stream(run_id, after_sequence=after_sequence):
                yield {
                    "id": str(ev.sequence),
                    "event": "run_event",
                    "data": json.dumps(
                        RunEventOut.model_validate(ev).model_dump(mode="json"),
                        ensure_ascii=False,
                    ),
                }
        finally:
            db.close()

    return EventSourceResponse(event_generator())


@router.post("/{run_id}/cancel", response_model=ApiResponse[RunOut])
def cancel_run(run_id: str, db: Session = Depends(get_db)) -> ApiResponse:
    body = {}  # 预留 reason 字段,后续接入请求体
    run = RunService(db).cancel(run_id, reason=body.get("reason"))
    return ApiResponse.ok(RunOut.model_validate(run))
