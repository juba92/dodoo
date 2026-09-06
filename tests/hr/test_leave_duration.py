"""US2 — leave duration vs. working calendar + public holidays (FR-025, needs Postgres)."""

from __future__ import annotations

import pytest

from dodoo.core.exceptions import DodooError


@pytest.fixture
async def setup(env, company_id):
    from dodoo.addons.hr.models.hr_employee import HrEmployee
    from dodoo.addons.hr.models.hr_leave_allocation import HrLeaveAllocation
    from dodoo.addons.hr.models.hr_leave_type import HrLeaveType

    emp = await HrEmployee.create(env, {"name": "Leaver", "company_id": company_id})
    ptype = await HrLeaveType.create(
        env, {"name": "PTO-D", "request_unit": "day", "approval_mode": "manager"}
    )
    await HrLeaveAllocation.create(
        env, {"employee_id": emp, "leave_type_id": ptype, "company_id": company_id, "number_of_units": 20}
    )
    return {"company_id": company_id, "emp": emp, "ptype": ptype}


async def test_weekend_excluded(env, setup):
    from dodoo.addons.hr.models.hr_leave import HrLeave

    # 2026-06-01 is a Monday; Mon..Sun span → 5 working days.
    units = await HrLeave._leave_duration(
        env, setup["company_id"], "2026-06-01T00:00:00", "2026-06-07T23:59:59", "day"
    )
    assert units == 5


async def test_public_holiday_excluded(env, setup):
    from dodoo.addons.hr.models.hr_leave import HrLeave
    from dodoo.addons.hr.models.hr_public_holiday import HrPublicHoliday

    await HrPublicHoliday.create(
        env, {"name": "Mid-week", "date_from": "2026-06-03", "date_to": "2026-06-03"}
    )
    units = await HrLeave._leave_duration(
        env, setup["company_id"], "2026-06-01T00:00:00", "2026-06-07T23:59:59", "day"
    )
    assert units == 4  # one working day removed


async def test_hour_unit(env, setup):
    from dodoo.addons.hr.models.hr_leave import HrLeave

    hours = await HrLeave._leave_duration(
        env, setup["company_id"], "2026-06-01T00:00:00", "2026-06-01T23:59:59", "hour"
    )
    assert hours == 8  # one weekday: 08-12 + 13-17


async def test_zero_day_request_rejected(env, setup):
    from dodoo.addons.hr.models.hr_leave import HrLeave

    with pytest.raises(DodooError, match="leave_zero_days"):
        await HrLeave.create(
            env,
            {
                "employee_id": setup["emp"],
                "leave_type_id": setup["ptype"],
                "date_from": "2026-06-06T00:00:00",  # Saturday
                "date_to": "2026-06-07T23:59:59",  # Sunday
            },
        )
