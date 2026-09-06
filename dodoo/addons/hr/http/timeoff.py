"""REST action routes for Time Off (US2)."""

from __future__ import annotations

from fastapi import Request

from dodoo.addons.hr.http import json_err, json_ok
from dodoo.addons.hr.validators import LeaveApprove, LeaveRefuse, require_groups, validate
from dodoo.core.context import get_uid
from dodoo.core.exceptions import AccessError, DodooError
from dodoo.http.routing import route


@route("/hr/leave/{leave_id}/approve", methods=["POST"], auth="session")
async def leave_approve(request: Request, leave_id: int):
    env = request.app.state.env
    uid = get_uid()
    try:
        payload = validate(LeaveApprove, await request.json())
        from dodoo.addons.hr.models.hr_leave import HrLeave

        result = await HrLeave.action_approve(
            env, [leave_id], uid, expected_state=payload.expected_state
        )
        return json_ok(result)
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/hr/leave/{leave_id}/refuse", methods=["POST"], auth="session")
async def leave_refuse(request: Request, leave_id: int):
    env = request.app.state.env
    uid = get_uid()
    try:
        payload = validate(LeaveRefuse, await request.json())
        from dodoo.addons.hr.models.hr_leave import HrLeave

        await HrLeave.action_refuse(
            env, [leave_id], uid, reason=payload.reason, expected_state=payload.expected_state
        )
        return json_ok({"id": leave_id, "state": "refused"})
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/hr/cron/leave-accrual", methods=["POST"], auth="session")
async def cron_leave_accrual(request: Request):
    env = request.app.state.env
    try:
        await require_groups(env, get_uid(), "HR Administrator")
        from dodoo.addons.hr.models.hr_leave_allocation import HrLeaveAllocation

        return json_ok(await HrLeaveAllocation.run_leave_accrual(env))
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))
