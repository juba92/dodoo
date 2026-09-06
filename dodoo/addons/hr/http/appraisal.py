"""REST action routes for Appraisals (US4)."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy import text

from dodoo.addons.hr.http import json_err, json_ok
from dodoo.addons.hr.validators import (
    AppraisalLaunch,
    AppraisalSetState,
    is_member,
    validate,
)
from dodoo.core.context import get_uid
from dodoo.core.exceptions import AccessError, DodooError
from dodoo.http.routing import route


async def _may_manage(env, uid: int | None, employee_id: int) -> bool:
    """HR Officer/Administrator, or the appraisee's manager (their linked user)."""
    if await is_member(env, uid, "HR Officer") or await is_member(
        env, uid, "HR Administrator"
    ):
        return True
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT m.user_id FROM hr_employee e "
                "JOIN hr_employee m ON m.id = e.manager_id WHERE e.id = :e"
            ),
            {"e": employee_id},
        )
        r = row.fetchone()
    return bool(r and r[0] == uid)


@route("/hr/appraisal/launch", methods=["POST"], auth="session")
async def appraisal_launch(request: Request):
    env = request.app.state.env
    uid = get_uid()
    try:
        payload = validate(AppraisalLaunch, await request.json())
        if not await _may_manage(env, uid, payload.employee_id):
            raise AccessError("appraisal_not_authorized")
        from dodoo.addons.hr.models.hr_appraisal import HrAppraisal

        return json_ok(
            await HrAppraisal.action_launch(
                env, payload.employee_id, payload.template_id, uid
            )
        )
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/hr/appraisal/{appraisal_id}/set-state", methods=["POST"], auth="session")
async def appraisal_set_state(request: Request, appraisal_id: int):
    env = request.app.state.env
    uid = get_uid()
    try:
        payload = validate(AppraisalSetState, await request.json())
        from dodoo.addons.hr.models.hr_appraisal import HrAppraisal

        rows = await HrAppraisal.read(env, [appraisal_id], ["employee_id"])
        if not rows:
            raise DodooError("appraisal_not_found")
        if not await _may_manage(env, uid, rows[0]["employee_id"]):
            raise AccessError("appraisal_not_authorized")
        return json_ok(
            await HrAppraisal.action_set_state(
                env,
                [appraisal_id],
                payload.state,
                uid=uid,
                expected_state=payload.expected_state,
            )
        )
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))
