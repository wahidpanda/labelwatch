from typing import Any

from app.config import Settings
from app.db.repositories.health import HealthRepository
from app.db.session import create_engine, create_session_factory, session_scope


class FakeSession:
    def __init__(self, scalars: list[Any]) -> None:
        self._scalars = scalars
        self.executed: list[str] = []

    async def execute(self, statement: Any) -> None:
        self.executed.append(str(statement))

    async def scalar(self, statement: Any) -> Any:
        self.executed.append(str(statement))
        return self._scalars.pop(0)


async def test_engine_and_session_factory_build_without_connecting() -> None:
    engine = create_engine(Settings(env="test"))
    try:
        assert engine.dialect.name == "postgresql"
        factory = create_session_factory(engine)
        async for session in session_scope(factory):
            assert session.bind is engine
    finally:
        await engine.dispose()


async def test_schema_version_none_when_table_missing() -> None:
    session = FakeSession([None])
    repo = HealthRepository(session)  # type: ignore[arg-type]
    await repo.ping()
    assert await repo.schema_version() is None
    assert session.executed[0] == "select 1"


async def test_schema_version_reads_latest() -> None:
    repo = HealthRepository(FakeSession(["schema_migrations", "0003"]))  # type: ignore[arg-type]
    assert await repo.schema_version() == "0003"
