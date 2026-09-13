"""REST action routes for Physical Inventory Adjustments (US4)."""

from __future__ import annotations

from fastapi import Request

from dodoo.addons.stock.http import json_err, json_ok
from dodoo.addons.stock.security import GROUP_MANAGER, GROUP_USER
from dodoo.addons.stock.validators import CountApply, CountSet, require_groups, validate
from dodoo.core.context import get_uid
from dodoo.core.exceptions import AccessError, DodooError
from dodoo.http.routing import route


@route("/stock/inventory/count/set", methods=["POST"], auth="session")
async def count_set(request: Request):
    env = request.app.state.env
    try:
        await require_groups(env, get_uid(), GROUP_USER, GROUP_MANAGER)
        payload = validate(CountSet, await request.json())
        from dodoo.addons.stock.models.stock_quant import StockQuant

        updated = 0
        for line in payload.lines:
            await StockQuant.write(
                env, [line.quant_id], {"counted_quantity": line.counted_quantity}
            )
            updated += 1
        return json_ok({"updated": updated})
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/stock/inventory/count/apply", methods=["POST"], auth="session")
async def count_apply(request: Request):
    env = request.app.state.env
    uid = get_uid()
    try:
        await require_groups(env, uid, GROUP_USER, GROUP_MANAGER)
        payload = validate(CountApply, await request.json())
        from dodoo.addons.stock.models.stock_quant import StockQuant

        result = await StockQuant.apply_count(env, payload.quant_ids, uid=uid)
        return json_ok(result)
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))
