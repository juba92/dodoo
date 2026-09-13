"""REST action routes for Warehouses, Locations & Operation Types (US2)."""

from __future__ import annotations

from fastapi import Request

from dodoo.addons.stock.http import json_err, json_ok
from dodoo.addons.stock.security import GROUP_MANAGER, GROUP_USER
from dodoo.addons.stock.validators import require_groups
from dodoo.core.context import get_uid
from dodoo.core.exceptions import AccessError, DodooError
from dodoo.http.routing import route


@route("/stock/warehouse/{warehouse_id}/topology", methods=["GET"], auth="session")
async def warehouse_topology(request: Request, warehouse_id: int):
    env = request.app.state.env
    try:
        await require_groups(env, get_uid(), GROUP_USER, GROUP_MANAGER)
        from dodoo.addons.stock.models.stock_location import StockLocation
        from dodoo.addons.stock.models.stock_picking_type import StockPickingType

        loc_ids = await StockLocation.search(env, [["warehouse_id", "=", warehouse_id]])
        locations = (
            await StockLocation.read(env, loc_ids, ["name", "usage", "parent_id"])
            if loc_ids
            else []
        )
        type_ids = await StockPickingType.search(env, [["warehouse_id", "=", warehouse_id]])
        picking_types = (
            await StockPickingType.read(
                env,
                type_ids,
                ["name", "code", "default_location_src_id", "default_location_dest_id"],
            )
            if type_ids
            else []
        )
        return json_ok({"locations": locations, "picking_types": picking_types})
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/stock/warehouse/{warehouse_id}/apply-steps", methods=["POST"], auth="session")
async def warehouse_apply_steps(request: Request, warehouse_id: int):
    env = request.app.state.env
    try:
        await require_groups(env, get_uid(), GROUP_MANAGER)
        from dodoo.addons.stock.models.stock_warehouse import StockWarehouse

        result = await StockWarehouse.action_apply_steps(env, warehouse_id)
        return json_ok(result)
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))
