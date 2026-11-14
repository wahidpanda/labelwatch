from fastapi import APIRouter

from app.deps import OpsServiceDep
from app.services.ops import LlmOpsOverview

router = APIRouter(prefix="/ops", tags=["ops"])


@router.get("/llm", response_model=LlmOpsOverview)
async def get_llm_ops(service: OpsServiceDep) -> LlmOpsOverview:
    return await service.llm_overview()
