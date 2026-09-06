"""US2 — approval workflow: modes, self-approval escalation, refuse restores (ADR-025)."""

from __future__ import annotations

import pytest

from dodoo.core.exceptions import DodooError


@pytest.fixture
async def team(env, company_id):
    from sqlalchemy import text

    from dodoo.addons.hr.models.hr_employee import HrEmployee
    from dodoo.addons.hr.models.hr_leave_allocation import HrLeaveAllocation
    from dodoo.addons.hr.models.hr_leave_type import HrLeaveType
    from dodoo.addons.hr.security import assign_hr_group

    async with env.dml_conn() as conn:
        mgr_uid = (await conn.execute(text(
            "INSERT INTO res_users (login,name,active,create_date,write_date) "
            "VALUES ('mgr','Mgr',TRUE,now(),now()) RETURNING id"))).scalar_one()
        emp_uid = (await conn.execute(text(
            "INSERT INTO res_users (login,name,active,create_date,write_date) "
            "VALUES ('e','E',TRUE,now(),now()) RETURNING id"))).scalar_one()
        off_uid = (await conn.execute(text(
            "INSERT INTO res_users (login,name,active,create_date,write_date) "
            "VALUES ('o','O',TRUE,now(),now()) RETURNING id"))).scalar_one()
        await conn.commit()
    await assign_hr_group(env, emp_uid, "employee")
    await assign_hr_group(env, mgr_uid, "employee")
    await assign_hr_group(env, off_uid, "officer")

    mgr = await HrEmployee.create(env, {"name": "Mgr", "company_id": company_id, "user_id": mgr_uid})
    emp = await HrEmployee.create(
        env, {"name": "E", "company_id": company_id, "user_id": emp_uid, "manager_id": mgr}
    )
    lt = await HrLeaveType.create(
        env, {"name": "Mgr PTO", "approval_mode": "manager", "allocation_required": True}
    )
    await HrLeaveAllocation.create(
        env, {"employee_id": emp, "leave_type_id": lt, "company_id": company_id, "number_of_units": 20}
    )
    return {"mgr_uid": mgr_uid, "emp_uid": emp_uid, "off_uid": off_uid, "emp": emp, "mgr": mgr, "lt": lt}


async def test_manager_approves_and_balance_drops(env, team, company_id):
    from dodoo.addons.hr.models.hr_leave import HrLeave

    lid = await HrLeave.create(
        env,
        {
            "employee_id": team["emp"],
            "leave_type_id": team["lt"],
            "date_from": "2026-06-01T00:00:00",
            "date_to": "2026-06-05T23:59:59",
        },
    )
    before = await HrLeave.get_balance(env, team["emp"], team["lt"])
    res = await HrLeave.action_approve(env, [lid], team["mgr_uid"])
    assert res["state"] == "approved"
    after = await HrLeave.get_balance(env, team["emp"], team["lt"])
    assert after["taken"] == before["pending"] + before["taken"]
    assert after["available"] == before["available"]  # pending → taken, net unchanged


async def test_requester_cannot_self_approve(env, team):
    from dodoo.addons.hr.models.hr_leave import HrLeave

    # make the employee also a manager of themselves-ish: they are their own leave's requester
    lid = await HrLeave.create(
        env,
        {
            "employee_id": team["emp"],
            "leave_type_id": team["lt"],
            "date_from": "2026-07-01T00:00:00",
            "date_to": "2026-07-03T23:59:59",
        },
    )
    with pytest.raises(DodooError, match="leave_not_authorized"):
        await HrLeave.action_approve(env, [lid], team["emp_uid"])
    # an officer can still approve (escalation target)
    res = await HrLeave.action_approve(env, [lid], team["off_uid"])
    assert res["state"] == "approved"


async def test_refuse_after_approve_restores_balance(env, team):
    from dodoo.addons.hr.models.hr_leave import HrLeave

    lid = await HrLeave.create(
        env,
        {
            "employee_id": team["emp"],
            "leave_type_id": team["lt"],
            "date_from": "2026-08-03T00:00:00",
            "date_to": "2026-08-07T23:59:59",
        },
    )
    await HrLeave.action_approve(env, [lid], team["mgr_uid"])
    mid = await HrLeave.get_balance(env, team["emp"], team["lt"])
    assert mid["taken"] > 0
    await HrLeave.action_refuse(env, [lid], team["mgr_uid"], reason="changed plans")
    end = await HrLeave.get_balance(env, team["emp"], team["lt"])
    assert end["taken"] == 0


async def test_overlap_rejected(env, team):
    from dodoo.addons.hr.models.hr_leave import HrLeave

    await HrLeave.create(
        env,
        {
            "employee_id": team["emp"],
            "leave_type_id": team["lt"],
            "date_from": "2026-09-07T00:00:00",
            "date_to": "2026-09-11T23:59:59",
        },
    )
    with pytest.raises(DodooError, match="leave_overlap"):
        await HrLeave.create(
            env,
            {
                "employee_id": team["emp"],
                "leave_type_id": team["lt"],
                "date_from": "2026-09-09T00:00:00",
                "date_to": "2026-09-14T23:59:59",
            },
        )


async def test_insufficient_balance_rejected(env, team, company_id):
    from dodoo.addons.hr.models.hr_leave import HrLeave
    from dodoo.addons.hr.models.hr_leave_type import HrLeaveType

    tight = await HrLeaveType.create(
        env, {"name": "Tight", "allocation_required": True, "allow_negative": False}
    )
    with pytest.raises(DodooError, match="leave_insufficient_balance"):
        await HrLeave.create(
            env,
            {
                "employee_id": team["emp"],
                "leave_type_id": tight,
                "date_from": "2026-10-05T00:00:00",
                "date_to": "2026-10-09T23:59:59",
            },
        )
