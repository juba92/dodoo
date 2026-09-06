"""Schema + seed assertions for the fleet addon (extended per US6). Requires PostgreSQL."""

from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio

EXPECTED_TABLES: list[str] = []


async def test_fleet_manager_group_seeded(env):
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT 1 FROM res_groups WHERE name = 'Fleet Manager'")
        )
    assert row.fetchone()


async def test_expected_tables_present(env):
    if not EXPECTED_TABLES:
        pytest.skip("no fleet tables expected yet (models land in US6)")
    async with env.dml_conn() as conn:
        rows = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
        )
        present = {r[0] for r in rows}
    missing = [t for t in EXPECTED_TABLES if t not in present]
    assert not missing, f"missing tables: {missing}"
