from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.db.repositories.catalog import CatalogRepository
from app.db.repositories.health import HealthRepository
from app.services.catalog import CatalogService
from app.services.health import HealthService


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_health_service(session: SessionDep, settings: SettingsDep) -> HealthService:
    return HealthService(HealthRepository(session), build_sha=settings.build_sha)


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]


def get_catalog_service(session: SessionDep, settings: SettingsDep) -> CatalogService:
    return CatalogService(CatalogRepository(session), stale_days=settings.stale_days)


CatalogServiceDep = Annotated[CatalogService, Depends(get_catalog_service)]
