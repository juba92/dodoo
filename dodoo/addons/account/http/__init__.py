from __future__ import annotations

import logging
import pathlib

from fastapi import Request
from fastapi.responses import JSONResponse

from dodoo.http.routing import MountRegistry, route
from dodoo.http.static import NoCacheStaticFiles

_STATIC_DIR = pathlib.Path(__file__).parent.parent / "static"

MountRegistry.get().add_mount(
    "/account/static",
    NoCacheStaticFiles(directory=str(_STATIC_DIR)),
    name="account_static",
)

_log = logging.getLogger(__name__)


@route("/account/move/{move_id}/post", methods=["POST"], auth="session")
async def action_post_move(request: Request, move_id: int) -> JSONResponse:
    env = request.app.state.env
    from dodoo.addons.account.models.account_move import AccountMove

    try:
        await AccountMove.action_post(env, [move_id])
        return JSONResponse({"result": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/move/{move_id}/reset_to_draft", methods=["POST"], auth="session")
async def action_reset_move(request: Request, move_id: int) -> JSONResponse:
    env = request.app.state.env
    from dodoo.addons.account.models.account_move import AccountMove

    try:
        await AccountMove.action_reset_to_draft(env, [move_id])
        return JSONResponse({"result": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/move/{move_id}/reverse", methods=["POST"], auth="session")
async def action_reverse_move(request: Request, move_id: int) -> JSONResponse:
    env = request.app.state.env
    from dodoo.addons.account.models.account_move import AccountMove

    body = await request.json()
    date = body.get("date")
    journal_id = body.get("journal_id")

    try:
        reversal_ids = await AccountMove.action_reverse(
            env, [move_id], date=date, journal_id=journal_id
        )
        return JSONResponse({"result": reversal_ids})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/payment/{payment_id}/post", methods=["POST"], auth="session")
async def action_post_payment(request: Request, payment_id: int) -> JSONResponse:
    env = request.app.state.env
    from dodoo.addons.account.models.account_payment import AccountPayment

    try:
        await AccountPayment.action_post(env, [payment_id])
        return JSONResponse({"result": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/payment/{payment_id}/register", methods=["POST"], auth="session")
async def register_payment(request: Request, payment_id: int) -> JSONResponse:
    env = request.app.state.env
    from dodoo.addons.account.models.account_payment import AccountPayment

    body = await request.json()
    invoice_ids = body.get("invoice_ids", [])

    try:
        result = await AccountPayment.register_against_invoices(
            env, payment_id, invoice_ids
        )
        return JSONResponse({"result": result})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/report/trial-balance", methods=["GET"], auth="session")
async def trial_balance(request: Request) -> JSONResponse:
    env = request.app.state.env
    from dodoo.addons.account.models.account_report import AccountReportTrialBalance

    params = dict(request.query_params)
    try:
        result = await AccountReportTrialBalance.get_report(
            env,
            date_from=params.get("date_from"),
            date_to=params.get("date_to"),
        )
        return JSONResponse({"result": result})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
