"""PERF-001 / SC-009 — employee directory list/search first page < 500 ms at 2,000 employees.

Requires PostgreSQL (uses the tests/hr install fixture); skips without Docker/TEST_DATABASE_URL.
"""

from __future__ import annotations

import time

import pytest

_N = 2000
_BUDGET_MS = 500


@pytest.fixture
async def big_directory(env, company_id):
    from sqlalchemy import text

    async with env.dml_conn() as conn:
        existing = await conn.execute(
            text("SELECT COUNT(*) FROM hr_employee WHERE company_id = :c"),
            {"c": company_id},
        )
        if existing.scalar_one() >= _N:
            return
        await conn.execute(
            text(
                "INSERT INTO hr_employee (name, company_id, active, create_date, write_date) "
                "SELECT 'Employee ' || g, :c, TRUE, now(), now() "
                "FROM generate_series(1, :n) AS g"
            ),
            {"c": company_id, "n": _N},
        )
        await conn.commit()


async def test_directory_first_page_under_budget(env, big_directory):
    from dodoo.addons.hr.models.hr_employee import HrEmployee

    t0 = time.perf_counter()
    rows = await HrEmployee.search_read(
        env,
        [["name", "ilike", "Employee 1%"]],
        fields=["id", "name", "department_id", "job_id"],
        limit=50,
        order="name",
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert rows, "expected results"
    assert elapsed_ms < _BUDGET_MS, f"directory search took {elapsed_ms:.0f}ms (budget {_BUDGET_MS}ms)"
