"""US4 — appraisal cycle: state machine, per-side feedback visibility, next date (ADR-026)."""

from __future__ import annotations

import datetime

import pytest

from dodoo.addons.hr.models.hr_appraisal import _TRANSITIONS, _add_months
from dodoo.core.exceptions import AccessError, DodooError

# ---- pure logic ------------------------------------------------------------


def test_transition_table():
    assert _TRANSITIONS["new"] == {"pending_confirmation", "cancelled"}
    assert _TRANSITIONS["confirmed"] == {"done", "cancelled"}
    assert _TRANSITIONS["done"] == set()
    assert _TRANSITIONS["cancelled"] == set()


def test_add_months_clamps_day():
    assert _add_months(datetime.date(2026, 1, 31), 1) == datetime.date(2026, 2, 28)
    assert _add_months(datetime.date(2026, 6, 15), 12) == datetime.date(2027, 6, 15)


# ---- DB-backed (skips without Postgres) ----------------------------------


@pytest.fixture
async def appraisal_setup(env, company_id):
    from sqlalchemy import text

    from dodoo.addons.hr.models.hr_appraisal_template import (
        HrAppraisalFeedbackSection,
        HrAppraisalTemplate,
    )
    from dodoo.addons.hr.models.hr_employee import HrEmployee
    from dodoo.addons.hr.security import assign_hr_group

    async with env.dml_conn() as conn:
        emp_uid = (await conn.execute(text(
            "INSERT INTO res_users (login,name,active,create_date,write_date) "
            "VALUES ('ae','AE',TRUE,now(),now()) RETURNING id"))).scalar_one()
        mgr_uid = (await conn.execute(text(
            "INSERT INTO res_users (login,name,active,create_date,write_date) "
            "VALUES ('am','AM',TRUE,now(),now()) RETURNING id"))).scalar_one()
        await conn.commit()
    await assign_hr_group(env, emp_uid, "employee")
    await assign_hr_group(env, mgr_uid, "officer")

    mgr = await HrEmployee.create(env, {"name": "AM", "company_id": company_id, "user_id": mgr_uid})
    emp = await HrEmployee.create(
        env, {"name": "AE", "company_id": company_id, "user_id": emp_uid, "manager_id": mgr}
    )
    tpl = await HrAppraisalTemplate.create(env, {"name": "T", "default_frequency_months": 12})
    await HrAppraisalFeedbackSection.create(env, {"template_id": tpl, "title": "S1"})
    await HrAppraisalFeedbackSection.create(env, {"template_id": tpl, "title": "S2"})
    return {"emp": emp, "mgr": mgr, "emp_uid": emp_uid, "mgr_uid": mgr_uid, "tpl": tpl}


async def test_launch_instantiates_both_sides(env, appraisal_setup):
    from dodoo.addons.hr.models.hr_appraisal import HrAppraisal
    from dodoo.addons.hr.models.hr_appraisal_feedback import HrAppraisalFeedback

    res = await HrAppraisal.action_launch(
        env, appraisal_setup["emp"], appraisal_setup["tpl"], appraisal_setup["mgr_uid"]
    )
    aid = res["appraisal_id"]
    fb_ids = await HrAppraisalFeedback.search(env, [["appraisal_id", "=", aid]])
    rows = await HrAppraisalFeedback.read(env, fb_ids)  # officer context: sees all
    assert len(rows) == 4  # 2 sections x 2 sides
    assert {r["side"] for r in rows} == {"employee", "manager"}


async def test_state_machine_and_conflict(env, appraisal_setup):
    from dodoo.addons.hr.models.hr_appraisal import HrAppraisal

    aid = (await HrAppraisal.action_launch(
        env, appraisal_setup["emp"], appraisal_setup["tpl"], appraisal_setup["mgr_uid"]))["appraisal_id"]
    await HrAppraisal.action_set_state(env, [aid], "pending_confirmation", uid=appraisal_setup["mgr_uid"])
    with pytest.raises(DodooError, match="appraisal_transition_invalid"):
        await HrAppraisal.action_set_state(env, [aid], "done", uid=appraisal_setup["mgr_uid"])
    with pytest.raises(DodooError, match="appraisal_state_conflict"):
        await HrAppraisal.action_set_state(
            env, [aid], "confirmed", uid=appraisal_setup["mgr_uid"], expected_state="new"
        )


async def test_done_sets_next_appraisal_date(env, appraisal_setup):
    from dodoo.addons.hr.models.hr_appraisal import HrAppraisal
    from dodoo.addons.hr.models.hr_employee import HrEmployee

    aid = (await HrAppraisal.action_launch(
        env, appraisal_setup["emp"], appraisal_setup["tpl"], appraisal_setup["mgr_uid"]))["appraisal_id"]
    for st in ("pending_confirmation", "confirmed", "done"):
        res = await HrAppraisal.action_set_state(env, [aid], st, uid=appraisal_setup["mgr_uid"])
    assert res["next_appraisal_date"] == _add_months(datetime.date.today(), 12).isoformat()
    emp = await HrEmployee.read(env, [appraisal_setup["emp"]], ["next_appraisal_date"])
    assert str(emp[0]["next_appraisal_date"])[:10] == res["next_appraisal_date"]


async def test_feedback_visibility_between_sides(env, appraisal_setup):
    from dodoo.addons.hr.models.hr_appraisal import HrAppraisal
    from dodoo.addons.hr.models.hr_appraisal_feedback import HrAppraisalFeedback
    from dodoo.core.context import set_uid

    aid = (await HrAppraisal.action_launch(
        env, appraisal_setup["emp"], appraisal_setup["tpl"], appraisal_setup["mgr_uid"]))["appraisal_id"]
    fb_ids = await HrAppraisalFeedback.search(env, [["appraisal_id", "=", aid]])
    all_rows = await HrAppraisalFeedback.read(env, fb_ids)
    emp_row = next(r for r in all_rows if r["side"] == "employee")

    # employee writes their own feedback, not visible
    set_uid(appraisal_setup["emp_uid"])
    try:
        await HrAppraisalFeedback.write(env, [emp_row["id"]], {"content": "secret", "is_visible": False})
        # manager cannot see the hidden employee row
        set_uid(appraisal_setup["mgr_uid"])
        mgr_view = await HrAppraisalFeedback.read(env, fb_ids)
        assert not any(r["id"] == emp_row["id"] for r in mgr_view)
        # employee turns it visible → manager now sees it
        set_uid(appraisal_setup["emp_uid"])
        await HrAppraisalFeedback.write(env, [emp_row["id"]], {"is_visible": True})
        set_uid(appraisal_setup["mgr_uid"])
        mgr_view2 = await HrAppraisalFeedback.read(env, fb_ids)
        assert any(r["id"] == emp_row["id"] for r in mgr_view2)
    finally:
        set_uid(None)


async def test_manager_cannot_write_employee_feedback(env, appraisal_setup):
    from dodoo.addons.hr.models.hr_appraisal import HrAppraisal
    from dodoo.addons.hr.models.hr_appraisal_feedback import HrAppraisalFeedback
    from dodoo.core.context import set_uid

    aid = (await HrAppraisal.action_launch(
        env, appraisal_setup["emp"], appraisal_setup["tpl"], appraisal_setup["mgr_uid"]))["appraisal_id"]
    fb_ids = await HrAppraisalFeedback.search(env, [["appraisal_id", "=", aid]])
    emp_row = next(r for r in await HrAppraisalFeedback.read(env, fb_ids) if r["side"] == "employee")
    set_uid(appraisal_setup["mgr_uid"])
    try:
        with pytest.raises(AccessError, match="feedback_wrong_side"):
            await HrAppraisalFeedback.write(env, [emp_row["id"]], {"content": "nope"})
    finally:
        set_uid(None)


async def test_cancel_and_history(env, appraisal_setup):
    from dodoo.addons.hr.models.hr_appraisal import HrAppraisal

    aid = (await HrAppraisal.action_launch(
        env, appraisal_setup["emp"], appraisal_setup["tpl"], appraisal_setup["mgr_uid"]))["appraisal_id"]
    await HrAppraisal.action_set_state(env, [aid], "cancelled", uid=appraisal_setup["mgr_uid"])
    hist = await HrAppraisal.get_history(env, appraisal_setup["emp"])
    assert hist[0]["state"] == "cancelled"


async def test_resolve_appraiser_falls_back_to_officer(env, company_id):
    from sqlalchemy import text

    from dodoo.addons.hr.models.hr_appraisal import HrAppraisal
    from dodoo.addons.hr.models.hr_employee import HrEmployee
    from dodoo.addons.hr.security import assign_hr_group

    async with env.dml_conn() as conn:
        off_uid = (await conn.execute(text(
            "INSERT INTO res_users (login,name,active,create_date,write_date) "
            "VALUES ('off2','Off2',TRUE,now(),now()) RETURNING id"))).scalar_one()
        await conn.commit()
    await assign_hr_group(env, off_uid, "officer")
    orphan = await HrEmployee.create(env, {"name": "No Manager", "company_id": company_id})
    appraiser = await HrAppraisal._resolve_appraiser(env, orphan)
    assert appraiser == off_uid
