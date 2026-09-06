"""US3 — recruitment pipeline, refuse, hired stage, idempotent conversion (needs Postgres)."""

from __future__ import annotations

import pytest

from dodoo.core.exceptions import DodooError


@pytest.fixture
async def recruiting(env, company_id):
    from sqlalchemy import text

    from dodoo.addons.hr.models.hr_job import HrJob
    from dodoo.addons.hr.security import assign_hr_group

    async with env.dml_conn() as conn:
        uid = (await conn.execute(text(
            "INSERT INTO res_users (login,name,active,create_date,write_date) "
            "VALUES ('rec','Rec',TRUE,now(),now()) RETURNING id"))).scalar_one()
        await conn.commit()
    async with env.dml_conn() as conn:
        stages = await conn.execute(
            text("SELECT id, is_hired_stage FROM hr_recruitment_stage ORDER BY sequence")
        )
        stage_rows = stages.fetchall()
    await assign_hr_group(env, uid, "officer")
    job = await HrJob.create(
        env, {"name": "Recruiter Test Job", "company_id": company_id, "is_published": True}
    )
    return {
        "uid": uid,
        "job": job,
        "first_stage": stage_rows[0][0],
        "hired_stage": next(s[0] for s in stage_rows if s[1]),
    }


async def test_pipeline_groups_by_stage(env, recruiting):
    from dodoo.addons.hr.models.hr_applicant import HrApplicant

    await HrApplicant.create(env, {"partner_name": "A", "job_id": recruiting["job"]})
    await HrApplicant.create(env, {"partner_name": "B", "job_id": recruiting["job"]})
    pipe = await HrApplicant.get_pipeline(env, recruiting["job"])
    assert [s["name"] for s in pipe["stages"]][0] == "Initial Qualification"
    assert len(pipe["cards"][str(recruiting["first_stage"])]) == 2


async def test_stage_move_and_conflict(env, recruiting):
    from dodoo.addons.hr.models.hr_applicant import HrApplicant

    aid = await HrApplicant.create(env, {"partner_name": "C", "job_id": recruiting["job"]})
    res = await HrApplicant.action_set_stage(
        env, [aid], recruiting["hired_stage"], uid=recruiting["uid"],
        expected_stage_id=recruiting["first_stage"],
    )
    assert res["hired"] is True
    with pytest.raises(DodooError, match="applicant_stage_conflict"):
        await HrApplicant.action_set_stage(
            env, [aid], recruiting["first_stage"], uid=recruiting["uid"],
            expected_stage_id=recruiting["first_stage"],
        )


async def test_refuse_leaves_pipeline(env, recruiting):
    from sqlalchemy import text

    from dodoo.addons.hr.models.hr_applicant import HrApplicant

    async with env.dml_conn() as conn:
        reason = (await conn.execute(
            text("SELECT id FROM hr_applicant_refuse_reason LIMIT 1"))).scalar_one()
    aid = await HrApplicant.create(env, {"partner_name": "D", "job_id": recruiting["job"]})
    await HrApplicant.action_refuse(env, [aid], recruiting["uid"], reason)
    pipe = await HrApplicant.get_pipeline(env, recruiting["job"])
    all_ids = {c["id"] for cards in pipe["cards"].values() for c in cards}
    assert aid not in all_ids
    rows = await HrApplicant.read(env, [aid], ["refused", "refuse_reason_id"])
    assert rows[0]["refused"] is True and rows[0]["refuse_reason_id"] == reason


async def test_create_employee_idempotent_and_no_user(env, recruiting):
    from dodoo.addons.hr.models.hr_applicant import HrApplicant
    from dodoo.addons.hr.models.hr_employee import HrEmployee

    aid = await HrApplicant.create(
        env,
        {
            "partner_name": "Grace Hopper",
            "email_from": "grace@example.com",
            "partner_phone": "555",
            "job_id": recruiting["job"],
        },
    )
    first = await HrApplicant.create_employee(env, aid, recruiting["uid"])
    assert first["created"] is True
    second = await HrApplicant.create_employee(env, aid, recruiting["uid"])
    assert second["created"] is False
    assert second["employee_id"] == first["employee_id"]

    emp = await HrEmployee.read(env, [first["employee_id"]], ["name", "work_email", "user_id"])
    assert emp[0]["name"] == "Grace Hopper"
    assert emp[0]["work_email"] == "grace@example.com"
    assert emp[0]["user_id"] is None  # never auto-provisioned
