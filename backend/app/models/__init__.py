"""ORM 模型集合。

导入所有模型以便 Alembic autogenerate 能发现它们,
并使 `Base.metadata` 包含全部表定义。
"""

from app.models.artifact import Artifact
from app.models.run import Run
from app.models.run_event import RunEvent
from app.models.run_step import RunStep
from app.models.task import Task

__all__ = ["Task", "Run", "RunStep", "RunEvent", "Artifact"]
