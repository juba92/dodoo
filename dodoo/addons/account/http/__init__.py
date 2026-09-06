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


@route("/account/account/{account_id}/balance", methods=["GET"], auth="session")
async def account_balance(request: Request, account_id: int) -> JSONResponse:
    """Debit / credit / net total of every posted line on one account (spec US-5 AC-5)."""
    env = request.app.state.env
    from dodoo.addons.account.models.account_account import AccountAccount

    try:
        return JSONResponse({"result": await AccountAccount.get_balance(env, account_id)})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=400)


def _q(request: Request, key: str) -> str | None:
    v = request.query_params.get(key)
    return v or None


@route("/account/report/trial-balance", methods=["GET"], auth="session")
async def report_trial_balance(request: Request) -> JSONResponse:
    from dodoo.addons.account.models.account_report import AccountReportTrialBalance

    try:
        return JSONResponse(
            await AccountReportTrialBalance.get_report(
                request.app.state.env,
                date_from=_q(request, "date_from"),
                date_to=_q(request, "date_to"),
            )
        )
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/report/general-ledger", methods=["GET"], auth="session")
async def report_general_ledger(request: Request) -> JSONResponse:
    from dodoo.addons.account.models.account_report import AccountReportGeneralLedger

    acc = _q(request, "account_id")
    try:
        return JSONResponse(
            await AccountReportGeneralLedger.get_report(
                request.app.state.env,
                account_id=int(acc) if acc else None,
                date_from=_q(request, "date_from"),
                date_to=_q(request, "date_to"),
            )
        )
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/report/profit-loss", methods=["GET"], auth="session")
async def report_profit_loss(request: Request) -> JSONResponse:
    from dodoo.addons.account.models.account_report import AccountReportProfitLoss

    try:
        return JSONResponse(
            await AccountReportProfitLoss.get_report(
                request.app.state.env,
                date_from=_q(request, "date_from"),
                date_to=_q(request, "date_to"),
            )
        )
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/report/balance-sheet", methods=["GET"], auth="session")
async def report_balance_sheet(request: Request) -> JSONResponse:
    from dodoo.addons.account.models.account_report import AccountReportBalanceSheet

    try:
        return JSONResponse(
            await AccountReportBalanceSheet.get_report(
                request.app.state.env, date=_q(request, "date")
            )
        )
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/report/aged-receivable", methods=["GET"], auth="session")
async def report_aged_receivable(request: Request) -> JSONResponse:
    from dodoo.addons.account.models.account_report import AccountReportAgedReceivable

    try:
        return JSONResponse(
            await AccountReportAgedReceivable.get_report(
                request.app.state.env, date=_q(request, "date")
            )
        )
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/report/aged-payable", methods=["GET"], auth="session")
async def report_aged_payable(request: Request) -> JSONResponse:
    from dodoo.addons.account.models.account_report import AccountReportAgedPayable

    try:
        return JSONResponse(
            await AccountReportAgedPayable.get_report(
                request.app.state.env, date=_q(request, "date")
            )
        )
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=400)
