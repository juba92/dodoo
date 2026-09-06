"""HR test fixtures: installs base+web+hr once per session (mirrors tests/accounting/)."""

from __future__ import annotations

import os

import pytest
import pytest_asyncio


def _pg_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or None


@pytest.fixture(scope="session")
def pg_container():
    existing_url = _pg_url()
    if existing_url:
        yield None
        return
    try:
        from testcontainers.postgres import PostgresContainer

        with PostgresContainer("postgres:15") as pg:
            yield pg
    except Exception as exc:
        pytest.skip(f"Docker unavailable for testcontainers: {exc}")


@pytest.fixture(scope="session")
def db_url(pg_container) -> str:
    existing_url = _pg_url()
    if existing_url:
        url = existing_url
    elif pg_container is not None:
        url = pg_container.get_connection_url().replace(
            "postgresql://", "postgresql+asyncpg://"
        )
    else:
        pytest.skip("No PostgreSQL available")
        return ""

    os.environ["DATABASE_URL"] = url
    os.environ["DATABASE_MIGRATION_URL"] = url
    os.environ.setdefault("SESSION_EXPIRY_HOURS", "8")
    return url


@pytest.fixture(scope="session")
def modules_installed(db_url):
    """Install base+web+hr once per session in a dedicated event loop."""
    import asyncio

    async def _install():
        from dodoo import Environment
        from dodoo.http.routing import RouteRegistry

        RouteRegistry.reset()
        env = await Environment.create()
        from dodoo.modules.installer import ModuleInstaller

        installer = ModuleInstaller(env)
        await installer.install("hr")
        await env.close()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_install())
    finally:
        loop.close()


@pytest_asyncio.fixture
async def env(db_url, modules_installed):
    from dodoo import Environment
    from dodoo.http.routing import RouteRegistry

    RouteRegistry.reset()
    environment = await Environment.create()
    yield environment
    await environment.close()


@pytest_asyncio.fixture
async def company_id(env):
    from sqlalchemy import text

    async with env.dml_conn() as conn:
        row = await conn.execute(text("SELECT id FROM res_company LIMIT 1"))
        return row.scalar_one()


@pytest_asyncio.fixture
async def admin_uid(env):
    from sqlalchemy import text

    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT id FROM res_users WHERE login = 'admin' LIMIT 1")
        )
        return row.scalar_one()
