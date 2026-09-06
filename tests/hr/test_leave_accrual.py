"""US2 — accrual tick + cap + idempotency (FR-023, ADR-025)."""

from __future__ import annotations

import datetime

import pytest

from dodoo.addons.hr.models.hr_leave_allocation import _PERIOD_DAYS
from dodoo.core.exceptions import DodooError


def test_period_day_map():
    assert _PERIOD_DAYS == {"day": 1, "week": 7, "month": 30}


def test_accrual_config_guard():
    from dodoo.addons.hr.models.hr_leave_allocation import HrLeaveAllocation

    with pytest.raises(DodooError, match="accrual_config_invalid"):
        HrLeaveAllocation._check_accrual({"mode": "accrual", "accrual_rate": 0})
    HrLeaveAllocation._check_accrual({"mode": "accrual", "accrual_rate": 1, "accrual_period": "month"})
    HrLeaveAllocation._check_accrual({"mode": "regular"})


@pytest.fixture
async def accrual(env, company_id):
    from dodoo.addons.hr.models.hr_employee import HrEmployee
    from dodoo.addons.hr.models.hr_leave_allocation import HrLeaveAllocation
    from dodoo.addons.hr.models.hr_leave_type import HrLeaveType

    emp = await HrEmployee.create(env, {"name": "Accruer", "company_id": company_id})
    lt = await HrLeaveType.create(env, {"name": "Accrued PTO"})
    two_months_ago = (datetime.date.today() - datetime.timedelta(days=65)).isoformat()
    aid = await HrLeaveAllocation.create(
        env,
        {
            "employee_id": emp,
            "leave_type_id": lt,
            "company_id": company_id,
            "mode": "accrual",
            "accrual_rate": 1.0,
            "accrual_period": "month",
            "accrual_max": 12.0,
            "last_accrual_date": two_months_ago,
        },
    )
    return {"aid": aid}


async def test_accrual_adds_per_period_and_is_idempotent(env, accrual):
    from dodoo.addons.hr.models.hr_leave_allocation import HrLeaveAllocation

    first = await HrLeaveAllocation.run_leave_accrual(env)
    assert first["updated"] == 1
    assert first["units_added"] == pytest.approx(2.0)  # two elapsed months

    rows = await HrLeaveAllocation.read(env, [accrual["aid"]], ["number_of_units"])
    assert rows[0]["number_of_units"] == pytest.approx(2.0)

    second = await HrLeaveAllocation.run_leave_accrual(env)
    assert second["units_added"] == pytest.approx(0.0)


async def test_accrual_respects_cap(env, company_id):
    from dodoo.addons.hr.models.hr_employee import HrEmployee
    from dodoo.addons.hr.models.hr_leave_allocation import HrLeaveAllocation
    from dodoo.addons.hr.models.hr_leave_type import HrLeaveType

    emp = await HrEmployee.create(env, {"name": "Capped", "company_id": company_id})
    lt = await HrLeaveType.create(env, {"name": "Capped PTO"})
    old = (datetime.date.today() - datetime.timedelta(days=400)).isoformat()
    await HrLeaveAllocation.create(
        env,
        {
            "employee_id": emp,
            "leave_type_id": lt,
            "company_id": company_id,
            "mode": "accrual",
            "accrual_rate": 1.0,
            "accrual_period": "month",
            "accrual_max": 5.0,
            "last_accrual_date": old,
        },
    )
    await HrLeaveAllocation.run_leave_accrual(env)
    ids = await HrLeaveAllocation.search(env, [["employee_id", "=", emp]])
    rows = await HrLeaveAllocation.read(env, ids, ["number_of_units"])
    assert rows[0]["number_of_units"] == pytest.approx(5.0)
