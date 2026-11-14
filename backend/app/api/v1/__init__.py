from fastapi import APIRouter

from app.api.v1 import alerts, bd, catalog, chat, eval, health, leaflets, medicines, ops

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(catalog.router)
api_router.include_router(medicines.router)
api_router.include_router(leaflets.router)
api_router.include_router(bd.router)
api_router.include_router(alerts.router)
api_router.include_router(chat.router)
api_router.include_router(eval.router)
api_router.include_router(ops.router)
