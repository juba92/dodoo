"""REST action routes for Employees / Contracts (US1)."""

from __future__ import annotations

from fastapi import Request

from dodoo.addons.hr.http import json_err, json_ok
from dodoo.addons.hr.validators import ContractSetState, require_groups, validate
from dodoo.core.context import get_uid
from dodoo.core.exceptions import AccessError, DodooError
from dodoo.http.routing import route


@route("/hr/contract/{contract_id}/set-state", methods=["POST"], auth="session")
async def contract_set_state(request: Request, contract_id: int):
    env = request.app.state.env
    uid = get_uid()
    try:
        payload = validate(ContractSetState, await request.json())
        await require_groups(env, uid, "HR Officer", "HR Administrator")
        from dodoo.addons.hr.models.hr_contract import HrContract

        await HrContract.action_set_state(
            env,
            [contract_id],
            payload.state,
            uid=uid,
            expected_state=payload.expected_state,
        )
        return json_ok({"id": contract_id, "state": payload.state})
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/hr/cron/contract-expiry", methods=["POST"], auth="session")
async def cron_contract_expiry(request: Request):
    env = request.app.state.env
    try:
        await require_groups(env, get_uid(), "HR Administrator")
        from dodoo.addons.hr.models.hr_contract import HrContract

        return json_ok(await HrContract.run_contract_expiry(env))
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/hr/employee/{employee_id}/org-chart", methods=["GET"], auth="session")
async def employee_org_chart(request: Request, employee_id: int):
    env = request.app.state.env
    try:
        await require_groups(
            env, get_uid(), "HR Employee", "HR Officer", "HR Administrator"
        )
        from dodoo.addons.hr.models.hr_employee import HrEmployee

        return json_ok(await HrEmployee.get_org_chart(env, employee_id))
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))
