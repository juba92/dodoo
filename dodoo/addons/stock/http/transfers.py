"""REST action routes for Transfers & Stock Moves (US3)."""

from __future__ import annotations

from fastapi import Request

from dodoo.addons.stock.http import json_err, json_ok
from dodoo.addons.stock.security import GROUP_MANAGER, GROUP_USER
from dodoo.addons.stock.validators import (
    TransferCancel,
    TransferCreate,
    TransferValidate,
    require_groups,
    validate,
)
from dodoo.core.context import get_uid
from dodoo.core.exceptions import AccessError, DodooError
from dodoo.http.routing import route


@route("/stock/picking", methods=["POST"], auth="session")
async def create_picking(request: Request):
    env = request.app.state.env
    uid = get_uid()
    try:
        await require_groups(env, uid, GROUP_USER, GROUP_MANAGER)
        payload = validate(TransferCreate, await request.json())
        from dodoo.addons.stock.models.stock_picking import StockPicking

        picking_id = await StockPicking.create_with_moves(
            env,
            {
                "picking_type_id": payload.picking_type_id,
                "partner_id": payload.partner_id,
                "scheduled_date": payload.scheduled_date,
            },
            [m.model_dump() for m in payload.moves],
        )
        return json_ok({"picking_id": picking_id})
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/stock/picking/{picking_id}/confirm", methods=["POST"], auth="session")
async def confirm_picking(request: Request, picking_id: int):
    env = request.app.state.env
    uid = get_uid()
    try:
        await require_groups(env, uid, GROUP_USER, GROUP_MANAGER)
        from dodoo.addons.stock.models.stock_move import StockMove
        from dodoo.addons.stock.models.stock_picking import StockPicking

        state = await StockPicking.action_confirm(env, picking_id, uid=uid)
        move_ids = await StockMove.search(env, [["picking_id", "=", picking_id]])
        moves = await StockMove.read(env, move_ids, ["state"]) if move_ids else []
        return json_ok(
            {
                "state": state,
                "moves": [{"move_id": m["id"], "state": m["state"]} for m in moves],
            }
        )
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/stock/picking/{picking_id}/validate", methods=["POST"], auth="session")
async def validate_picking(request: Request, picking_id: int):
    env = request.app.state.env
    uid = get_uid()
    try:
        await require_groups(env, uid, GROUP_USER, GROUP_MANAGER)
        payload = validate(TransferValidate, await request.json())
        from dodoo.addons.stock.models.stock_picking import StockPicking

        result = await StockPicking.action_validate(
            env,
            picking_id,
            uid=uid,
            expected_state=payload.expected_state,
            create_backorder=payload.create_backorder,
        )
        return json_ok(result)
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc), status_code=409 if "conflict" in str(exc) else 400)


@route("/stock/picking/{picking_id}/cancel", methods=["POST"], auth="session")
async def cancel_picking(request: Request, picking_id: int):
    env = request.app.state.env
    uid = get_uid()
    try:
        await require_groups(env, uid, GROUP_USER, GROUP_MANAGER)
        payload = validate(TransferCancel, await request.json())
        from dodoo.addons.stock.models.stock_picking import StockPicking

        state = await StockPicking.action_cancel(
            env, picking_id, uid=uid, expected_state=payload.expected_state
        )
        return json_ok({"state": state})
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc), status_code=409 if "conflict" in str(exc) else 400)


@route("/stock/picking/{picking_id}/return", methods=["POST"], auth="session")
async def return_picking(request: Request, picking_id: int):
    env = request.app.state.env
    uid = get_uid()
    try:
        await require_groups(env, uid, GROUP_USER, GROUP_MANAGER)
        from dodoo.addons.stock.models.stock_picking import StockPicking

        return_picking_id = await StockPicking.action_return(env, picking_id, uid=uid)
        return json_ok({"return_picking_id": return_picking_id})
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))


@route("/stock/product/{product_id}/forecast", methods=["GET"], auth="session")
async def product_forecast(request: Request, product_id: int):
    env = request.app.state.env
    try:
        await require_groups(env, get_uid(), GROUP_USER, GROUP_MANAGER)
        location_id = request.query_params.get("location_id")
        from dodoo.addons.stock.models.stock_quant import StockQuant

        result = await StockQuant.get_forecast(
            env, product_id, int(location_id) if location_id else None
        )
        return json_ok(result)
    except AccessError as exc:
        return json_err(str(exc), status_code=403)
    except DodooError as exc:
        return json_err(str(exc))
