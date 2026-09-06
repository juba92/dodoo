"""REST action route for Referrals (US5)."""

from __future__ import annotations

from fastapi import Request

from dodoo.addons.hr.http import json_err, json_ok
from dodoo.addons.hr.validators import ReferralSubmit, validate
from dodoo.core.context import get_uid
from dodoo.core.exceptions import AccessError, DodooError
from dodoo.http.routing import route


@route("/hr/referral/submit", methods=["POST"], auth="session")
async def referral_submit(request: Request):
    env = request.app.state.env
    uid = get_uid()
    try:
        payload = validate(ReferralSubmit, await request.json())
        from dodoo.addons.hr.models.hr_referral import HrReferral

        return json_ok(await HrReferral.action_submit(env, payload.model_dump(), uid))
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))
