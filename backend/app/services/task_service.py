"""Task 业务服务。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import TaskNotFound
from app.models import Task
from app.schemas.task import TaskCreate, TaskUpdate


class TaskService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, payload: TaskCreate) -> Task:
        task = Task(
            title=payload.title,
            description=payload.description,
            status="draft",
            priority=payload.priority,
            input=payload.input,
            metadata_=payload.metadata,
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def get(self, task_id: str) -> Task:
        task = self.db.get(Task, task_id)
        if not task:
            raise TaskNotFound(f"Task {task_id} not found")
        return task

    def list(
        self,
        status: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> list[Task]:
        stmt = select(Task).order_by(Task.created_at.desc(), Task.id.desc())
        if status:
            stmt = stmt.where(Task.status == status)
        if cursor:
            stmt = stmt.where(Task.id < cursor)
        stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt))

    def update(self, task_id: str, payload: TaskUpdate) -> Task:
        task = self.get(task_id)
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            if key == "metadata":
                task.metadata_ = value
            else:
                setattr(task, key, value)
        self.db.commit()
        self.db.refresh(task)
        return task
