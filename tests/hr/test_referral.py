"""US5 — employee referrals into recruitment (FR-046…FR-050, needs Postgres)."""

from __future__ import annotations

import pytest

from dodoo.core.exceptions import DodooError


@pytest.fixture
async def referrer(env, company_id):
    from sqlalchemy import text

    from dodoo.addons.hr.models.hr_employee import HrEmployee
    from dodoo.addons.hr.models.hr_job import HrJob
    from dodoo.addons.hr.security import assign_hr_group

    async with env.dml_conn() as conn:
        uid = (await conn.execute(text(
            "INSERT INTO res_users (login,name,active,create_date,write_date) "
            "VALUES ('ref','Ref',TRUE,now(),now()) RETURNING id"))).scalar_one()
        await conn.commit()
    await assign_hr_group(env, uid, "employee")
    emp = await HrEmployee.create(env, {"name": "Ref", "company_id": company_id, "user_id": uid})
    pub = await HrJob.create(
        env, {"name": "Open Role", "company_id": company_id, "is_published": True}
    )
    closed = await HrJob.create(
        env, {"name": "Draft Role", "company_id": company_id, "is_published": False}
    )
    return {"uid": uid, "emp": emp, "pub": pub, "closed": closed}


async def test_submit_creates_linked_applicant(env, referrer):
    from dodoo.addons.hr.models.hr_applicant import HrApplicant
    from dodoo.addons.hr.models.hr_referral import HrReferral
    from dodoo.core.context import set_uid

    set_uid(referrer["uid"])
    try:
        res = await HrReferral.action_submit(
            env,
            {"job_id": referrer["pub"], "candidate_name": "Cara", "candidate_email": "cara@x.io"},
        )
    finally:
        set_uid(None)
    app_rows = await HrApplicant.read(
        env, [res["applicant_id"]], ["partner_name", "referral_id", "source_id", "job_id"]
    )
    assert app_rows[0]["partner_name"] == "Cara"
    assert app_rows[0]["referral_id"] == res["referral_id"]
    ref_rows = await HrReferral.read(env, [res["referral_id"]], None)
    assert ref_rows[0]["applicant_id"] == res["applicant_id"]
    assert ref_rows[0]["status"] == "Initial Qualification"


async def test_unpublished_job_rejected(env, referrer):
    from dodoo.addons.hr.models.hr_referral import HrReferral
    from dodoo.core.context import set_uid

    set_uid(referrer["uid"])
    try:
        with pytest.raises(DodooError, match="referral_job_unpublished"):
            await HrReferral.action_submit(
                env, {"job_id": referrer["closed"], "candidate_name": "Nope"}
            )
    finally:
        set_uid(None)


async def test_status_follows_pipeline_and_hire(env, referrer):
    from sqlalchemy import text

    from dodoo.addons.hr.models.hr_applicant import HrApplicant
    from dodoo.addons.hr.models.hr_referral import HrReferral
    from dodoo.core.context import set_uid

    set_uid(referrer["uid"])
    try:
        res = await HrReferral.action_submit(
            env, {"job_id": referrer["pub"], "candidate_name": "Dana"}
        )
    finally:
        set_uid(None)

    async with env.dml_conn() as conn:
        stage2 = (await conn.execute(text(
            "SELECT id FROM hr_recruitment_stage ORDER BY sequence OFFSET 1 LIMIT 1"))).scalar_one()
    await HrApplicant.action_set_stage(env, [res["applicant_id"]], stage2, uid=1)
    ref = await HrReferral.read(env, [res["referral_id"]], ["status"])
    assert ref[0]["status"] == "First Interview"

    await HrApplicant.create_employee(env, res["applicant_id"], uid=1)
    stats = await HrReferral.get_referrer_stats(env, referrer["emp"])
    assert stats == {"total": 1, "hired": 1}
    ref2 = await HrReferral.read(env, [res["referral_id"]], ["status"])
    assert ref2[0]["status"] == "hired"


async def test_referral_record_rule_scopes_to_owner(env, referrer, company_id):
    from sqlalchemy import text

    from dodoo.addons.hr.models.hr_employee import HrEmployee
    from dodoo.addons.hr.models.hr_referral import HrReferral
    from dodoo.addons.hr.security import assign_hr_group
    from dodoo.core.context import set_uid

    set_uid(referrer["uid"])
    try:
        await HrReferral.action_submit(env, {"job_id": referrer["pub"], "candidate_name": "Mine"})
    finally:
        set_uid(None)

    async with env.dml_conn() as conn:
        other_uid = (await conn.execute(text(
            "INSERT INTO res_users (login,name,active,create_date,write_date) "
            "VALUES ('other','Other',TRUE,now(),now()) RETURNING id"))).scalar_one()
        await conn.commit()
    await assign_hr_group(env, other_uid, "employee")
    await HrEmployee.create(env, {"name": "Other", "company_id": company_id, "user_id": other_uid})

    seen_by_other = await HrReferral.search(env, [], uid=other_uid)
    assert seen_by_other == []
    seen_by_owner = await HrReferral.search(env, [], uid=referrer["uid"])
    assert len(seen_by_owner) == 1
