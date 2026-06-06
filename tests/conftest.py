from __future__ import annotations

import os

import pytest
import pytest_asyncio

from dodoo import Environment
from dodoo.core.db import create_dml_engine


def _pg_url() -> str | None:
    """Return a PostgreSQL URL from env if already provided (skips Docker)."""
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or None


@pytest.fixture(scope="session")
def pg_container():
    """Spin up a PostgreSQL testcontainer, or skip if Docker is unavailable."""
    existing_url = _pg_url()
    if existing_url:
        # Yield a sentinel — pg_engine will use the existing URL directly
        yield None
        return

    try:
        from testcontainers.postgres import PostgresContainer

        with PostgresContainer("postgres:15") as pg:
            yield pg
    except Exception as exc:
        pytest.skip(f"Docker unavailable for testcontainers: {exc}")


@pytest_asyncio.fixture(scope="session")
async def pg_engine(pg_container):
    existing_url = _pg_url()
    if existing_url:
        url = existing_url
    elif pg_container is not None:
        url = pg_container.get_connection_url().replace("postgresql://", "postgresql+asyncpg://")
    else:
        pytest.skip("No PostgreSQL available")
        return

    os.environ["DATABASE_URL"] = url
    os.environ["DATABASE_MIGRATION_URL"] = url
    os.environ.setdefault("SESSION_EXPIRY_HOURS", "8")

    engine = create_dml_engine()
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def env(pg_engine):
    from dodoo.http.routing import RouteRegistry

    RouteRegistry.reset()

    environment = await Environment.create()
    yield environment
    await environment.close()
