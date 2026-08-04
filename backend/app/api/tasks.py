"""Task 相关路由。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import ApiResponse, Page
from app.schemas.task import TaskCreate, TaskDetailOut, TaskOut, TaskRunSummary, TaskUpdate
from app.services import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=ApiResponse[TaskOut])
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> ApiResponse:
    task = TaskService(db).create(payload)
    return ApiResponse.ok(TaskOut.model_validate(task))


@router.get("", response_model=ApiResponse[Page[TaskOut]])
def list_tasks(
    status: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse:
    tasks = TaskService(db).list(status=status, limit=limit, cursor=cursor)
    items = [TaskOut.model_validate(t) for t in tasks]
    next_cursor = items[-1].id if len(items) == limit else None
    return ApiResponse.ok(Page(items=items, next_cursor=next_cursor))


@router.get("/{task_id}", response_model=ApiResponse[TaskDetailOut])
def get_task(task_id: str, db: Session = Depends(get_db)) -> ApiResponse:
    task = TaskService(db).get(task_id)
    runs = [
        TaskRunSummary(id=r.id, status=r.status, workflow_name=r.workflow_name, created_at=r.created_at)
        for r in sorted(task.runs, key=lambda r: r.created_at, reverse=True)
    ]
    detail = TaskDetailOut(
        **TaskOut.model_validate(task).model_dump(by_alias=False, exclude_unset=True),
        runs=runs,
    )
    return ApiResponse.ok(detail)


@router.patch("/{task_id}", response_model=ApiResponse[TaskOut])
def update_task(task_id: str, payload: TaskUpdate, db: Session = Depends(get_db)) -> ApiResponse:
    task = TaskService(db).update(task_id, payload)
    return ApiResponse.ok(TaskOut.model_validate(task))
