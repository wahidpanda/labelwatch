from fastapi import APIRouter

from app.api.v1 import catalog, health, leaflets, medicines

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(catalog.router)
api_router.include_router(medicines.router)
api_router.include_router(leaflets.router)
