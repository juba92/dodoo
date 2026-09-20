"""Accounting test fixtures: installs base+account, seeds data once per session."""
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
    """Return the database URL and set env vars for the session."""
    existing_url = _pg_url()
    if existing_url:
        url = existing_url
    elif pg_container is not None:
        url = pg_container.get_connection_url().replace("postgresql://", "postgresql+asyncpg://")
    else:
        pytest.skip("No PostgreSQL available")
        return ""

    os.environ["DATABASE_URL"] = url
    os.environ["DATABASE_MIGRATION_URL"] = url
    os.environ.setdefault("SESSION_EXPIRY_HOURS", "8")
    return url


@pytest.fixture(scope="session")
def modules_installed(db_url):
    """Run module installation once per session using a dedicated event loop.

    After installation completes the engine is disposed so its connections
    (created in this session loop) are released before any test function
    picks up its own function-scoped loop.
    """
    import asyncio

    async def _install():
        from dodoo import Environment
        from dodoo.http.routing import RouteRegistry

        RouteRegistry.reset()
        env = await Environment.create()
        from dodoo.modules.installer import ModuleInstaller

        installer = ModuleInstaller(env)
        await installer.install("account")
        await env.close()  # dispose all pool connections

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_install())
    finally:
        loop.close()


@pytest_asyncio.fixture
async def env(db_url, modules_installed):
    """Fresh Environment per test function — connections belong to the function loop."""
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
async def currency_id(env):
    from sqlalchemy import text

    async with env.dml_conn() as conn:
        row = await conn.execute(text("SELECT id FROM res_currency WHERE code='EUR' LIMIT 1"))
        return row.scalar_one()


@pytest_asyncio.fixture
async def journal_sale(env, company_id):
    from sqlalchemy import text

    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT id FROM account_journal WHERE type='sale' AND company_id=:cid LIMIT 1"),
            {"cid": company_id},
        )
        return row.scalar_one()


@pytest_asyncio.fixture
async def ar_account(env, company_id):
    from sqlalchemy import text

    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT id FROM account_account "
                "WHERE account_type='asset_receivable' AND company_id=:cid LIMIT 1"
            ),
            {"cid": company_id},
        )
        return row.scalar_one()


@pytest_asyncio.fixture
async def revenue_account(env, company_id):
    from sqlalchemy import text

    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT id FROM account_account "
                "WHERE code='4000' AND company_id=:cid LIMIT 1"
            ),
            {"cid": company_id},
        )
        return row.scalar_one()


@pytest_asyncio.fixture
async def partner_id(env, company_id):
    from sqlalchemy import text

    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT id FROM res_partner WHERE company_id=:cid LIMIT 1"),
            {"cid": company_id},
        )
        r = row.fetchone()
        if r:
            return r[0]
    from dodoo.addons.base.models.res_partner import ResPartner

    return await ResPartner.create(
        env,
        {"name": "Test Partner", "company_id": company_id, "active": True},
    )


@pytest_asyncio.fixture
async def payment_term_id(env, company_id):
    from dodoo.addons.account.models.account_payment_term import AccountPaymentTerm

    return await AccountPaymentTerm.create(
        env, {"name": "Immediate", "company_id": company_id}
    )


@pytest_asyncio.fixture
async def customer_id(env, company_id, currency_id, payment_term_id):
    """009-customer-database: a partner flagged as a customer (`customer_rank > 0`)
    with billing address and default payment terms set."""
    from dodoo.addons.base.models.res_partner import ResPartner

    return await ResPartner.create(
        env,
        {
            "name": "Test Customer",
            "company_id": company_id,
            "active": True,
            "email": "customer@example.test",
            "phone": "+1-555-0100",
            "street": "1 Main St",
            "city": "Springfield",
            "zip": "00000",
            "vat": "US000111222",
            "customer_rank": 1,
            "property_payment_term_id": payment_term_id,
            "property_currency_id": currency_id,
        },
    )


@pytest_asyncio.fixture
async def vendor_id(env, company_id, currency_id, payment_term_id):
    """010-vendor-database: a partner flagged as a vendor (`supplier_rank > 0`) with
    billing address and default payment terms set.

    Built via the proven two-step ``ResPartner.create`` + ``write_partner_properties``
    shape (not a single ``create`` call with the raw columns inline) — those raw,
    undeclared columns (`supplier_rank`/`property_supplier_payment_term_id`/
    `property_currency_id`) are silently dropped by the generic `create` path, per
    `account_partner.py`'s own module docstring.
    """
    from dodoo.addons.account.models.account_partner import write_partner_properties
    from dodoo.addons.base.models.res_partner import ResPartner

    partner_id = await ResPartner.create(
        env,
        {
            "name": "Test Vendor",
            "company_id": company_id,
            "active": True,
            "email": "vendor@example.test",
            "phone": "+1-555-0200",
            "street": "9 Industrial Way",
            "city": "Riverside",
            "zip": "00001",
            "vat": "US000333444",
        },
    )
    await write_partner_properties(
        env,
        partner_id,
        {
            "supplier_rank": 1,
            "property_supplier_payment_term_id": payment_term_id,
            "property_currency_id": currency_id,
        },
    )
    return partner_id
