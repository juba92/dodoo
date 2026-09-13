"""REST action route for Scrap confirmation (US7)."""

from __future__ import annotations

from fastapi import Request

from dodoo.addons.stock.http import json_err, json_ok
from dodoo.addons.stock.security import GROUP_MANAGER, GROUP_USER
from dodoo.addons.stock.validators import require_groups
from dodoo.core.context import get_uid
from dodoo.core.exceptions import AccessError, DodooError
from dodoo.http.routing import route


@route("/stock/scrap/{scrap_id}/confirm", methods=["POST"], auth="session")
async def confirm_scrap(request: Request, scrap_id: int):
    env = request.app.state.env
    uid = get_uid()
    try:
        await require_groups(env, uid, GROUP_USER, GROUP_MANAGER)
        from dodoo.addons.stock.models.stock_scrap import StockScrap

        result = await StockScrap.action_confirm(env, scrap_id, uid=uid)
        return json_ok(result)
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))
