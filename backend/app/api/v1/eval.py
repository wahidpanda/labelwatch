import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.db.models import EvalRun
from app.deps import SessionDep
from app.errors import AppError

router = APIRouter(prefix="/eval", tags=["evaluation"])


@router.get("/runs")
async def list_runs(session: SessionDep) -> list[dict[str, object]]:
    rows = await session.scalars(select(EvalRun).order_by(EvalRun.created_at.desc()).limit(20))
    return [
        {"id": r.id, "name": r.name, "method": r.method, "split": r.split, "metrics": r.metrics}
        for r in rows
    ]


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, session: SessionDep) -> dict[str, object]:
    row = await session.get(EvalRun, run_id)
    if row is None:
        raise AppError(404, "Run not found.")
    return {
        "id": row.id,
        "name": row.name,
        "method": row.method,
        "split": row.split,
        "metrics": row.metrics,
        "created_at": row.created_at,
    }
