"""Artifact 路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ArtifactNotFound
from app.db.session import get_db
from app.models import Artifact
from app.schemas.artifact import ArtifactOut
from app.schemas.common import ApiResponse, Page
from app.services import RunService

router = APIRouter(tags=["artifacts"])


@router.get("/runs/{run_id}/artifacts", response_model=ApiResponse[Page[ArtifactOut]])
def list_run_artifacts(run_id: str, db: Session = Depends(get_db)) -> ApiResponse:
    # 确认 run 存在(不存在会抛 RunNotFound)
    RunService(db).get(run_id)
    stmt = select(Artifact).where(Artifact.run_id == run_id).order_by(Artifact.created_at.asc())
    items = [ArtifactOut.model_validate(a) for a in db.scalars(stmt)]
    return ApiResponse.ok(Page(items=items, next_cursor=None))


@router.get("/artifacts/{artifact_id}", response_model=ApiResponse[ArtifactOut])
def get_artifact(artifact_id: str, db: Session = Depends(get_db)) -> ApiResponse:
    artifact = db.get(Artifact, artifact_id)
    if not artifact:
        raise ArtifactNotFound(f"Artifact {artifact_id} not found")
    return ApiResponse.ok(ArtifactOut.model_validate(artifact))
