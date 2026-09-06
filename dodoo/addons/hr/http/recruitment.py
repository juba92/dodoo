"""REST action routes for Recruitment (US3)."""

from __future__ import annotations

from fastapi import Request

from dodoo.addons.hr.http import json_err, json_ok
from dodoo.addons.hr.validators import (
    ApplicantRefuse,
    ApplicantSetStage,
    require_groups,
    validate,
)
from dodoo.core.context import get_uid
from dodoo.core.exceptions import AccessError, DodooError
from dodoo.http.routing import route

_RECRUITER = ("HR Officer", "HR Administrator")


@route("/hr/applicant/{applicant_id}/set-stage", methods=["POST"], auth="session")
async def applicant_set_stage(request: Request, applicant_id: int):
    env = request.app.state.env
    uid = get_uid()
    try:
        payload = validate(ApplicantSetStage, await request.json())
        await require_groups(env, uid, *_RECRUITER)
        from dodoo.addons.hr.models.hr_applicant import HrApplicant

        res = await HrApplicant.action_set_stage(
            env,
            [applicant_id],
            payload.stage_id,
            uid=uid,
            expected_stage_id=payload.expected_stage_id,
        )
        return json_ok(res)
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/hr/applicant/{applicant_id}/refuse", methods=["POST"], auth="session")
async def applicant_refuse(request: Request, applicant_id: int):
    env = request.app.state.env
    uid = get_uid()
    try:
        payload = validate(ApplicantRefuse, await request.json())
        await require_groups(env, uid, *_RECRUITER)
        from dodoo.addons.hr.models.hr_applicant import HrApplicant

        await HrApplicant.action_refuse(env, [applicant_id], uid, payload.refuse_reason_id)
        return json_ok({"id": applicant_id, "refused": True})
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/hr/applicant/{applicant_id}/create-employee", methods=["POST"], auth="session")
async def applicant_create_employee(request: Request, applicant_id: int):
    env = request.app.state.env
    uid = get_uid()
    try:
        await require_groups(env, uid, *_RECRUITER)
        from dodoo.addons.hr.models.hr_applicant import HrApplicant

        return json_ok(await HrApplicant.create_employee(env, applicant_id, uid))
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))
