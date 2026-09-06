"""US1 — record-rule matrix + sensitive-field drop (needs Postgres).

Extended by later user stories (US2 leave, US4 appraisal, US5 referral).
"""

from __future__ import annotations

import pytest


@pytest.fixture
async def users(env, company_id):
    """An Employee-group user and an Officer-group user, each linked to an employee."""
    from sqlalchemy import text

    from dodoo.addons.hr.models.hr_employee import HrEmployee
    from dodoo.addons.hr.security import assign_hr_group

    async with env.dml_conn() as conn:
        emp_uid = (
            await conn.execute(
                text(
                    "INSERT INTO res_users (login, name, active, create_date, write_date) "
                    "VALUES ('emp', 'Emp', TRUE, now(), now()) RETURNING id"
                )
            )
        ).scalar_one()
        off_uid = (
            await conn.execute(
                text(
                    "INSERT INTO res_users (login, name, active, create_date, write_date) "
                    "VALUES ('off', 'Off', TRUE, now(), now()) RETURNING id"
                )
            )
        ).scalar_one()
        await conn.commit()
    await assign_hr_group(env, emp_uid, "employee")
    await assign_hr_group(env, off_uid, "officer")

    e1 = await HrEmployee.create(
        env,
        {
            "name": "Emp Self",
            "company_id": company_id,
            "user_id": emp_uid,
            "identification_id": "SECRET-1",
            "bank_account": "IBAN-1",
        },
    )
    e2 = await HrEmployee.create(
        env,
        {
            "name": "Someone Else",
            "company_id": company_id,
            "identification_id": "SECRET-2",
            "bank_account": "IBAN-2",
        },
    )
    return {"emp_uid": emp_uid, "off_uid": off_uid, "e1": e1, "e2": e2}


async def test_employee_sees_public_directory_not_others_private(env, users):
    from dodoo.addons.hr.models.hr_employee import HrEmployee
    from dodoo.core.context import set_uid

    set_uid(users["emp_uid"])
    try:
        rows = await HrEmployee.read(env, [users["e1"], users["e2"]], None)
    finally:
        set_uid(None)
    by_id = {r["id"]: r for r in rows}
    # own record: sensitive fields visible
    assert by_id[users["e1"]]["identification_id"] == "SECRET-1"
    # other record: sensitive fields blanked
    assert by_id[users["e2"]]["identification_id"] is None
    assert by_id[users["e2"]]["bank_account"] is None
    # public fields still visible
    assert by_id[users["e2"]]["name"] == "Someone Else"


async def test_officer_sees_all_sensitive(env, users):
    from dodoo.addons.hr.models.hr_employee import HrEmployee
    from dodoo.core.context import set_uid

    set_uid(users["off_uid"])
    try:
        rows = await HrEmployee.read(env, [users["e2"]], None)
    finally:
        set_uid(None)
    assert rows[0]["identification_id"] == "SECRET-2"


async def test_contract_rule_scopes_employee_to_own(env, users, company_id):
    from dodoo.addons.hr.models.hr_contract import HrContract

    await HrContract.create(
        env,
        {"name": "own", "employee_id": users["e1"], "company_id": company_id, "date_start": "2026-01-01"},
    )
    await HrContract.create(
        env,
        {"name": "other", "employee_id": users["e2"], "company_id": company_id, "date_start": "2026-01-01"},
    )
    ids = await HrContract.search(env, [], uid=users["emp_uid"])
    names = {r["name"] for r in await HrContract.read(env, ids)}
    assert "own" in names and "other" not in names  # employee sees only their own

    off_ids = set(await HrContract.search(env, [], uid=users["off_uid"]))
    assert set(ids) <= off_ids  # officer sees at least everything the employee does
    off_names = {r["name"] for r in await HrContract.read(env, list(off_ids))}
    assert {"own", "other"} <= off_names
