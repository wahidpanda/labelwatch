from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.deps import HealthServiceDep
from app.services.health import HealthOut, ReadinessOut

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthOut)
async def healthz() -> HealthOut:
    return HealthOut(status="ok")


@router.get("/readyz", response_model=ReadinessOut, responses={503: {"model": ReadinessOut}})
async def readyz(service: HealthServiceDep) -> ReadinessOut | JSONResponse:
    result = await service.readiness()
    if result.status != "ok":
        return JSONResponse(result.model_dump(), status_code=503)
    return result
