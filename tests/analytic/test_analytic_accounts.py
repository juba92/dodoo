"""analytic.plan / analytic.account CRUD (data-model.md)."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_plan_and_account_crud(env, company_id):
    from dodoo.addons.analytic.models.analytic_account import AnalyticAccount
    from dodoo.addons.analytic.models.analytic_plan import AnalyticPlan

    plan_id = await AnalyticPlan.create(
        env, {"name": "Departments", "company_id": company_id}
    )
    account_id = await AnalyticAccount.create(
        env,
        {
            "name": "Marketing",
            "code": "MKT",
            "plan_id": plan_id,
            "company_id": company_id,
        },
    )

    rows = await AnalyticAccount.read(
        env, [account_id], ["name", "code", "plan_id", "active"]
    )
    assert rows[0]["name"] == "Marketing"
    assert rows[0]["code"] == "MKT"
    assert rows[0]["plan_id"] == plan_id
    assert rows[0]["active"] is True

    await AnalyticAccount.write(env, [account_id], {"name": "Marketing & Sales"})
    rows2 = await AnalyticAccount.read(env, [account_id], ["name"])
    assert rows2[0]["name"] == "Marketing & Sales"

    # Archiving keeps the row but flips active — used by the account-side
    # analytic_distribution validation (FR-038) to reject archived ids.
    await AnalyticAccount.write(env, [account_id], {"active": False})
    rows3 = await AnalyticAccount.read(env, [account_id], ["active"])
    assert rows3[0]["active"] is False


@pytest.mark.asyncio
async def test_plan_hierarchy(env, company_id):
    from dodoo.addons.analytic.models.analytic_plan import AnalyticPlan

    parent_id = await AnalyticPlan.create(env, {"name": "Company", "company_id": company_id})
    child_id = await AnalyticPlan.create(
        env, {"name": "Sub-Department", "parent_id": parent_id, "company_id": company_id}
    )
    rows = await AnalyticPlan.read(env, [child_id], ["parent_id"])
    assert rows[0]["parent_id"] == parent_id
