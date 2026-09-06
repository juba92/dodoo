"""US1 — org chart + department cycle (needs Postgres)."""

from __future__ import annotations

import pytest

from dodoo.core.exceptions import DodooError


async def test_org_chart_chain_and_reports(env, company_id):
    from dodoo.addons.hr.models.hr_employee import HrEmployee

    ceo = await HrEmployee.create(env, {"name": "CEO", "company_id": company_id})
    vp = await HrEmployee.create(env, {"name": "VP", "company_id": company_id, "manager_id": ceo})
    ic1 = await HrEmployee.create(env, {"name": "IC1", "company_id": company_id, "manager_id": vp})
    await HrEmployee.create(env, {"name": "IC2", "company_id": company_id, "manager_id": vp})

    chart = await HrEmployee.get_org_chart(env, vp)
    assert [n["name"] for n in chart["manager_chain"]] == ["CEO"]
    assert {n["name"] for n in chart["reports"]} == {"IC1", "IC2"}

    deep = await HrEmployee.get_org_chart(env, ic1)
    assert [n["name"] for n in deep["manager_chain"]] == ["CEO", "VP"]


async def test_department_cycle_rejected(env, company_id):
    from dodoo.addons.hr.models.hr_department import HrDepartment

    a = await HrDepartment.create(env, {"name": "A", "company_id": company_id})
    b = await HrDepartment.create(env, {"name": "B", "company_id": company_id, "parent_id": a})
    with pytest.raises(DodooError, match="department_cycle"):
        await HrDepartment.write(env, [a], {"parent_id": b})


async def test_department_complete_name(env, company_id):
    from dodoo.addons.hr.models.hr_department import HrDepartment

    a = await HrDepartment.create(env, {"name": "Sales", "company_id": company_id})
    b = await HrDepartment.create(env, {"name": "EMEA", "company_id": company_id, "parent_id": a})
    rows = await HrDepartment.read(env, [b], None)
    assert rows[0]["complete_name"] == "Sales / EMEA"
