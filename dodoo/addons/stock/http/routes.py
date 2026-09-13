"""REST action routes for Putaway Rules, Storage Categories, Routes & Reordering (US6)."""

from __future__ import annotations

from fastapi import Request

from dodoo.addons.stock.http import json_err, json_ok
from dodoo.addons.stock.security import GROUP_MANAGER, GROUP_USER
from dodoo.addons.stock.validators import RunReordering, require_groups, validate
from dodoo.core.context import get_uid
from dodoo.core.exceptions import AccessError, DodooError
from dodoo.http.routing import route


@route("/stock/putaway/resolve", methods=["GET"], auth="session")
async def putaway_resolve(request: Request):
    env = request.app.state.env
    try:
        await require_groups(env, get_uid(), GROUP_USER, GROUP_MANAGER)
        product_id = int(request.query_params["product_id"])
        source_location_id = int(request.query_params["source_location_id"])
        from dodoo.addons.stock.models.stock_putaway_rule import StockPutawayRule

        dest = await StockPutawayRule.resolve_destination(env, product_id, source_location_id)
        return json_ok({"destination_location_id": dest})
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/stock/orderpoint/run", methods=["POST"], auth="session")
async def orderpoint_run(request: Request):
    env = request.app.state.env
    uid = get_uid()
    try:
        await require_groups(env, uid, GROUP_MANAGER)
        payload = validate(RunReordering, await request.json())
        from dodoo.addons.stock.models.stock_orderpoint import StockWarehouseOrderpoint

        result = await StockWarehouseOrderpoint.run_reordering(
            env, payload.orderpoint_ids, uid=uid
        )
        return json_ok(result)
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))
