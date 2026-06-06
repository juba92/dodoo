import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from dodoo.core.exceptions import DodooError
from dodoo.core.logging import get_logger

_log = get_logger(__name__)


def _engine_for(url: str, **kwargs: object) -> AsyncEngine:
    try:
        return create_async_engine(url, **kwargs)
    except Exception as exc:
        raise DodooError(f"Database unavailable: {exc}") from exc


def create_dml_engine() -> AsyncEngine:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise DodooError("DATABASE_URL is not set")
    return _engine_for(url, pool_size=5, max_overflow=10)


def create_ddl_engine() -> AsyncEngine:
    url = os.environ.get("DATABASE_MIGRATION_URL", os.environ.get("DATABASE_URL", ""))
    if not url:
        raise DodooError("DATABASE_MIGRATION_URL is not set")
    return _engine_for(url, pool_size=2, max_overflow=0)


@asynccontextmanager
async def get_connection(engine: AsyncEngine) -> AsyncGenerator[AsyncConnection, None]:
    async with engine.begin() as conn:
        yield conn
