"""US1 — employee directory, headcount, tags, user link, company scope (needs Postgres)."""

from __future__ import annotations

import pytest

from dodoo.core.exceptions import DodooError


@pytest.fixture
async def base(env, company_id):
    from dodoo.addons.hr.models.hr_department import HrDepartment
    from dodoo.addons.hr.models.hr_job import HrJob

    dept = await HrDepartment.create(env, {"name": "Eng", "company_id": company_id})
    job = await HrJob.create(
        env, {"name": "Engineer", "company_id": company_id, "department_id": dept, "expected_employees": 2}
    )
    return {"company_id": company_id, "dept": dept, "job": job}


async def test_create_and_headcount(env, base):
    from dodoo.addons.hr.models.hr_employee import HrEmployee
    from dodoo.addons.hr.models.hr_job import HrJob

    await HrEmployee.create(
        env,
        {"name": "Ada", "company_id": base["company_id"], "job_id": base["job"], "department_id": base["dept"]},
    )
    await HrEmployee.create(
        env, {"name": "Linus", "company_id": base["company_id"], "job_id": base["job"]}
    )
    job = await HrJob.read(env, [base["job"]], None)
    assert job[0]["no_of_employees"] == 2


async def test_manager_cycle_rejected(env, base):
    from dodoo.addons.hr.models.hr_employee import HrEmployee

    a = await HrEmployee.create(env, {"name": "A", "company_id": base["company_id"]})
    b = await HrEmployee.create(env, {"name": "B", "company_id": base["company_id"], "manager_id": a})
    await HrEmployee.write(env, [a], {"manager_id": b})  # a→b, b→a is a cycle
    # the write above should raise; if it didn't, assert the guard explicitly
    with pytest.raises(DodooError, match="employee_cycle"):
        await HrEmployee.write(env, [a], {"manager_id": b})


async def test_user_unique_per_company(env, base):
    from dodoo.addons.hr.models.hr_employee import HrEmployee

    await HrEmployee.create(
        env, {"name": "Owner", "company_id": base["company_id"], "user_id": 1}
    )
    with pytest.raises(DodooError, match="user_already_linked"):
        await HrEmployee.create(
            env, {"name": "Other", "company_id": base["company_id"], "user_id": 1}
        )


async def test_resolve_current_none_without_link(env):
    from dodoo.addons.hr.models.hr_employee import HrEmployee

    res = await HrEmployee.resolve_current(env)
    assert res["employee_id"] is None
