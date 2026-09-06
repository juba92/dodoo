"""Schema + seed assertions for the hr addon.

Extended per user story with the tables/columns each one adds (data-model.md). For now it
covers the Phase 2 security scaffold. Requires PostgreSQL — skips otherwise (no Docker).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

# Filled in by later phases: table names that must exist after `install("hr")`.
EXPECTED_TABLES: list[str] = []

# Filled in by later phases: (table, column) pairs that must exist.
EXPECTED_COLUMNS: list[tuple[str, str]] = []


async def _tables(env) -> set[str]:
    async with env.dml_conn() as conn:
        rows = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
        )
        return {r[0] for r in rows}


async def test_hr_groups_seeded(env):
    async with env.dml_conn() as conn:
        rows = await conn.execute(
            text("SELECT name FROM res_groups WHERE name LIKE 'HR %'")
        )
        names = {r[0] for r in rows}
    assert {"HR Employee", "HR Officer", "HR Administrator"} <= names


async def test_ir_rule_junction_columns(env):
    """ADR-028 / base fix: ir_rule_group_rel must have rule_id / group_id columns."""
    async with env.dml_conn() as conn:
        rows = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'ir_rule_group_rel'"
            )
        )
        cols = {r[0] for r in rows}
    assert {"rule_id", "group_id"} <= cols


async def test_expected_tables_present(env):
    if not EXPECTED_TABLES:
        pytest.skip("no hr tables expected yet (models land per user story)")
    present = await _tables(env)
    missing = [t for t in EXPECTED_TABLES if t not in present]
    assert not missing, f"missing tables: {missing}"


async def test_expected_columns_present(env):
    if not EXPECTED_COLUMNS:
        pytest.skip("no additive columns expected yet")
    async with env.dml_conn() as conn:
        for table, column in EXPECTED_COLUMNS:
            row = await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = :c"
                ),
                {"t": table, "c": column},
            )
            assert row.fetchone(), f"missing column {table}.{column}"
