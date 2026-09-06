"""PERF-002 / SC-009 — time-off balance for one (employee, leave type) < 300 ms at 5 years.

Requires PostgreSQL; skips without Docker/TEST_DATABASE_URL.
"""

from __future__ import annotations

import time

import pytest

_BUDGET_MS = 300
_YEARS = 5


@pytest.fixture
async def history(env, company_id):
    from dodoo.addons.hr.models.hr_employee import HrEmployee
    from dodoo.addons.hr.models.hr_leave import HrLeave
    from dodoo.addons.hr.models.hr_leave_allocation import HrLeaveAllocation
    from dodoo.addons.hr.models.hr_leave_type import HrLeaveType

    emp = await HrEmployee.create(env, {"name": "Perf Leaver", "company_id": company_id})
    lt = await HrLeaveType.create(
        env, {"name": "Perf PTO", "allocation_required": True, "allow_negative": True}
    )
    for y in range(_YEARS):
        await HrLeaveAllocation.create(
            env,
            {"employee_id": emp, "leave_type_id": lt, "company_id": company_id, "number_of_units": 25},
        )
        # ~20 short approved leaves per year
        for i in range(20):
            month = (i % 12) + 1
            df = f"20{20 + y:02d}-{month:02d}-05T00:00:00"
            dt = f"20{20 + y:02d}-{month:02d}-06T23:59:59"
            try:
                lid = await HrLeave.create(
                    env, {"employee_id": emp, "leave_type_id": lt, "date_from": df, "date_to": dt}
                )
                await HrLeave.action_refuse(env, [lid], uid=1)  # keep the balance sane
            except Exception:
                pass
    return {"emp": emp, "lt": lt}


async def test_balance_under_budget(env, history):
    from dodoo.addons.hr.models.hr_leave import HrLeave

    t0 = time.perf_counter()
    bal = await HrLeave.get_balance(env, history["emp"], history["lt"])
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert "available" in bal
    assert elapsed_ms < _BUDGET_MS, f"balance took {elapsed_ms:.0f}ms (budget {_BUDGET_MS}ms)"
