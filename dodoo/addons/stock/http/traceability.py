"""REST action routes for Lots, Serial Numbers & Packages (US5)."""

from __future__ import annotations

from fastapi import Request

from dodoo.addons.stock.http import json_err, json_ok
from dodoo.addons.stock.security import GROUP_MANAGER, GROUP_USER
from dodoo.addons.stock.validators import PackageMove, TrackingUpdate, require_groups, validate
from dodoo.core.context import get_uid
from dodoo.core.exceptions import AccessError, DodooError
from dodoo.http.routing import route


@route("/stock/traceability/lot/{lot_id}", methods=["GET"], auth="session")
async def traceability_lot(request: Request, lot_id: int):
    env = request.app.state.env
    try:
        await require_groups(env, get_uid(), GROUP_USER, GROUP_MANAGER)
        from dodoo.addons.stock.models.stock_lot import StockLot

        lot = (await StockLot.read(env, [lot_id], ["product_id"]))[0]
        events = await StockLot.get_events(env, lot_id)
        return json_ok({"lot_id": lot_id, "product_id": lot["product_id"], "events": events})
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/stock/traceability/package/{package_id}", methods=["GET"], auth="session")
async def traceability_package(request: Request, package_id: int):
    env = request.app.state.env
    try:
        await require_groups(env, get_uid(), GROUP_USER, GROUP_MANAGER)
        from sqlalchemy import text

        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT ml.move_id, m.picking_id, m.create_date, ml.location_src_id, "
                    "ml.location_dest_id, ml.qty_done "
                    "FROM stock_move_line ml JOIN stock_move m ON m.id = ml.move_id "
                    "WHERE ml.package_id = :pkg OR ml.result_package_id = :pkg "
                    "ORDER BY m.create_date"
                ),
                {"pkg": package_id},
            )
            events = [dict(r._mapping) for r in rows]
        return json_ok({"package_id": package_id, "events": events})
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/stock/package/{package_id}/move", methods=["POST"], auth="session")
async def move_package(request: Request, package_id: int):
    env = request.app.state.env
    uid = get_uid()
    try:
        await require_groups(env, uid, GROUP_USER, GROUP_MANAGER)
        payload = validate(PackageMove, await request.json())
        from dodoo.addons.stock.models.stock_package import StockQuantPackage

        picking_id = await StockQuantPackage.move_package(
            env, package_id, payload.location_dest_id, uid=uid
        )
        return json_ok({"picking_id": picking_id})
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/stock/product/{product_id}/tracking", methods=["GET"], auth="session")
async def get_product_tracking(request: Request, product_id: int):
    env = request.app.state.env
    try:
        await require_groups(env, get_uid(), GROUP_USER, GROUP_MANAGER)
        from dodoo.addons.stock.models.product_product_ext import get_tracking

        tracking = await get_tracking(env, product_id)
        return json_ok({"product_id": product_id, "tracking": tracking})
    except AccessError as exc:
        return json_err(str(exc), status_code=403)


@route("/stock/product/{product_id}/tracking", methods=["POST"], auth="session")
async def set_product_tracking(request: Request, product_id: int):
    env = request.app.state.env
    uid = get_uid()
    try:
        await require_groups(env, uid, GROUP_MANAGER)
        payload = validate(TrackingUpdate, await request.json())
        from dodoo.addons.stock.models.product_product_ext import set_tracking

        await set_tracking(env, product_id, payload.tracking, uid=uid)
        return json_ok({"product_id": product_id, "tracking": payload.tracking})
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc), status_code=409)
