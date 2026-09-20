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
        warnings: list[str] = []
        await AccountMove.action_post(env, [move_id], _warnings=warnings)
        response: dict = {"result": True}
        if warnings:
            response["warning"] = warnings[0]
        return JSONResponse(response)
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


@route("/account/move/{move_id}/cancel", methods=["POST"], auth="session")
async def action_cancel_move(request: Request, move_id: int) -> JSONResponse:
    env = request.app.state.env
    from dodoo.addons.account.models.account_move import AccountMove

    try:
        await AccountMove.action_cancel(env, [move_id])
        return JSONResponse({"result": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/move/{move_id}/debit-note", methods=["POST"], auth="session")
async def action_create_debit_note(request: Request, move_id: int) -> JSONResponse:
    """FR-011. Empty body, per `DebitNoteCreate`."""
    env = request.app.state.env
    from dodoo.addons.account.models.account_move import AccountMove

    try:
        from dodoo.core.context import get_uid

        debit_note_id = await AccountMove.action_create_debit_note(env, move_id, get_uid())
        return JSONResponse({"result": debit_note_id})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/move/{move_id}/reverse", methods=["POST"], auth="session")
async def action_reverse_move(request: Request, move_id: int) -> JSONResponse:
    env = request.app.state.env
    from dodoo.addons.account.models.account_move import AccountMove

    body = await request.json()
    date = body.get("date")
    journal_id = body.get("journal_id")
    auto_post = body.get("auto_post", True)

    try:
        reversal_ids = await AccountMove.action_reverse(
            env, [move_id], date=date, journal_id=journal_id, auto_post=auto_post
        )
        state = "posted" if auto_post else "draft"
        return JSONResponse({"result": reversal_ids, "state": state})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/journal/{journal_id}/hash-chain", methods=["POST"], auth="session")
async def toggle_hash_chain(request: Request, journal_id: int) -> JSONResponse:
    """FR-007, ADR-039: only an Accounting Manager may enable/disable a
    journal's hash chain."""
    env = request.app.state.env
    from dodoo.addons.account.models.account_journal import AccountJournal
    from dodoo.addons.account.security import GROUP_MANAGER
    from dodoo.addons.account.validators import HashChainToggle, require_groups, validate

    body = await request.json()
    try:
        payload = validate(HashChainToggle, body)
        from dodoo.core.context import get_uid

        await require_groups(env, get_uid(), GROUP_MANAGER)
        await AccountJournal.write(
            env, [journal_id], {"restrict_mode_hash_table": payload.enabled}
        )
        _log.info(
            "account.journal hash chain toggled",
            extra={
                "model": "account.journal",
                "record_id": journal_id,
                "event": "toggle_hash_chain",
                "enabled": payload.enabled,
            },
        )
        return JSONResponse({"result": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/journal/{journal_id}/verify-hash-chain", methods=["GET"], auth="session")
async def verify_hash_chain(request: Request, journal_id: int) -> JSONResponse:
    env = request.app.state.env
    from dodoo.addons.account.models.account_move import AccountMove

    try:
        return JSONResponse(await AccountMove.verify_hash_chain(env, journal_id))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/lock-exception", methods=["POST"], auth="session")
async def grant_lock_exception(request: Request) -> JSONResponse:
    """FR-033, SEC-003: an Accounting Manager grants a time-boxed, scoped
    exception to a lock date; ``granted_by_id`` is set automatically."""
    env = request.app.state.env
    from dodoo.addons.account.models.account_lock_exception import AccountLockException
    from dodoo.addons.account.security import GROUP_MANAGER
    from dodoo.addons.account.validators import LockExceptionGrant, require_groups, validate

    body = await request.json()
    try:
        payload = validate(LockExceptionGrant, body)
        from dodoo.core.context import get_uid

        uid = get_uid()
        await require_groups(env, uid, GROUP_MANAGER)
        exception_id = await AccountLockException.create(
            env,
            {
                "company_id": payload.company_id,
                "lock_date_field": payload.lock_date_field,
                "lock_date": payload.lock_date,
                "user_id": payload.user_id,
                "journal_id": payload.journal_id,
                "end_date": payload.end_date,
                "granted_by_id": uid,
            },
        )
        _log.info(
            "account.lock.exception granted",
            extra={
                "model": "account.lock.exception",
                "record_id": exception_id,
                "event": "grant_lock_exception",
                "lock_date_field": payload.lock_date_field,
                "granted_by_id": uid,
            },
        )
        return JSONResponse({"result": exception_id})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/lock-exception/{exception_id}", methods=["DELETE"], auth="session")
async def revoke_lock_exception(request: Request, exception_id: int) -> JSONResponse:
    """FR-033: soft-revoke via ``active=False`` rather than deleting the audit row."""
    env = request.app.state.env
    from dodoo.addons.account.models.account_lock_exception import AccountLockException
    from dodoo.addons.account.security import GROUP_MANAGER
    from dodoo.addons.account.validators import require_groups

    try:
        from dodoo.core.context import get_uid

        await require_groups(env, get_uid(), GROUP_MANAGER)
        await AccountLockException.write(env, [exception_id], {"active": False})
        _log.info(
            "account.lock.exception revoked",
            extra={
                "model": "account.lock.exception",
                "record_id": exception_id,
                "event": "revoke_lock_exception",
            },
        )
        return JSONResponse({"result": True})
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


@route("/account/reconcile", methods=["POST"], auth="session")
async def reconcile_with_writeoff(request: Request) -> JSONResponse:
    """FR-020: direct-callable reconciliation, optionally with a write-off."""
    env = request.app.state.env
    from dodoo.addons.account.models.account_reconcile import AccountPartialReconcile
    from dodoo.addons.account.validators import ReconcileWithWriteOff, validate

    body = await request.json()
    try:
        payload = validate(ReconcileWithWriteOff, body)
        result = await AccountPartialReconcile.reconcile_lines(
            env,
            payload.debit_line_id,
            payload.credit_line_id,
            payload.amount,
            writeoff_account_id=payload.writeoff_account_id,
            writeoff_journal_id=payload.writeoff_journal_id,
        )
        return JSONResponse({"result": result})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/payment/{payment_id}/suggestions", methods=["GET"], auth="session")
async def payment_suggestions(request: Request, payment_id: int) -> JSONResponse:
    """FR-021: ranked, advisory-only reconciliation match suggestions."""
    env = request.app.state.env
    from dodoo.addons.account.models.account_reconcile import AccountPartialReconcile

    try:
        suggestions = await AccountPartialReconcile.suggest_matches(env, payment_id)
        return JSONResponse({"suggestions": suggestions})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/currency/revalue", methods=["POST"], auth="session")
async def currency_revalue(request: Request) -> JSONResponse:
    """FR-026: period-end unrealized currency gain/loss revaluation."""
    env = request.app.state.env
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.security import GROUP_MANAGER
    from dodoo.addons.account.validators import RunRevaluation, require_groups, validate

    body = await request.json()
    try:
        payload = validate(RunRevaluation, body)
        from dodoo.core.context import get_uid

        uid = get_uid()
        await require_groups(env, uid, GROUP_MANAGER)
        entries = await AccountMove.revalue_currency_balances(
            env, payload.company_id, payload.as_of, uid
        )
        return JSONResponse({"result": {"entries": entries}})
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


@route("/account/report/cash-flow", methods=["GET"], auth="session")
async def report_cash_flow(request: Request) -> JSONResponse:
    from dodoo.addons.account.models.account_report import AccountReportCashFlow

    try:
        return JSONResponse(
            await AccountReportCashFlow.get_report(
                request.app.state.env,
                date_from=_q(request, "date_from"),
                date_to=_q(request, "date_to"),
            )
        )
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/report/tax-report", methods=["GET"], auth="session")
async def report_tax(request: Request) -> JSONResponse:
    from dodoo.addons.account.models.account_report import AccountReportTax

    try:
        return JSONResponse(
            await AccountReportTax.get_report(
                request.app.state.env,
                date_from=_q(request, "date_from"),
                date_to=_q(request, "date_to"),
            )
        )
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/report/analytic", methods=["GET"], auth="session")
async def report_analytic(request: Request) -> JSONResponse:
    from dodoo.addons.account.models.account_report import AccountReportAnalytic

    try:
        return JSONResponse(
            await AccountReportAnalytic.get_report(
                request.app.state.env,
                date_from=_q(request, "date_from"),
                date_to=_q(request, "date_to"),
            )
        )
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/fiscal-year/close", methods=["POST"], auth="session")
async def fiscal_year_close(request: Request) -> JSONResponse:
    """FR-037. Requires "Accounting Manager"."""
    env = request.app.state.env
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.security import GROUP_MANAGER
    from dodoo.addons.account.validators import FiscalYearClose, require_groups, validate

    body = await request.json()
    try:
        payload = validate(FiscalYearClose, body)
        from dodoo.core.context import get_uid

        uid = get_uid()
        await require_groups(env, uid, GROUP_MANAGER)
        move_id = await AccountMove.close_fiscal_year(
            env, payload.company_id, payload.fiscal_year_end, uid
        )
        return JSONResponse({"result": move_id})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# ---- Bank statements (FR-027/028/029) ----


@route("/account/statement/{statement_id}/confirm", methods=["POST"], auth="session")
async def statement_confirm(request: Request, statement_id: int) -> JSONResponse:
    env = request.app.state.env
    from dodoo.addons.account.models.account_bank_statement import AccountBankStatement

    try:
        await AccountBankStatement.action_confirm(env, statement_id)
        return JSONResponse({"result": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/statement/{statement_id}/status", methods=["GET"], auth="session")
async def statement_status(request: Request, statement_id: int) -> JSONResponse:
    env = request.app.state.env
    from dodoo.addons.account.models.account_bank_statement import AccountBankStatement

    try:
        return JSONResponse(await AccountBankStatement.get_status(env, statement_id))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route(
    "/account/statement/{statement_id}/line/{line_id}/reconcile",
    methods=["POST"],
    auth="session",
)
async def statement_line_reconcile(
    request: Request, statement_id: int, line_id: int
) -> JSONResponse:
    env = request.app.state.env
    from dodoo.addons.account.models.account_bank_statement import AccountBankStatementLine
    from dodoo.addons.account.validators import StatementLineReconcile, validate

    body = await request.json()
    try:
        payload = validate(StatementLineReconcile, body)
        result = await AccountBankStatementLine.reconcile_against(
            env, line_id, payload.move_line_ids
        )
        return JSONResponse({"result": result})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# ---- Customer database (009-customer-database, FR-001/002/008/009/010) ----


@route("/account/customers", methods=["GET"], auth="session")
async def list_customers(request: Request) -> JSONResponse:
    """FR-003/004: customers (`customer_rank > 0`) for the list/search view —
    a raw route because `customer_rank` isn't a declared `Field` on `base`'s
    `ResPartner`, so the generic `search_read` domain compiler can't filter on
    it (ADR-046)."""
    env = request.app.state.env
    include_archived = request.query_params.get("include_archived") == "true"

    try:
        async with env.dml_conn() as conn:
            from sqlalchemy import text

            active_clause = "" if include_archived else "AND active = TRUE"
            rows = await conn.execute(
                text(
                    "SELECT id, name, vat, email, phone, active, customer_rank "
                    f"FROM res_partner WHERE customer_rank > 0 {active_clause} "  # noqa: S608
                    "ORDER BY name"
                )
            )
            return JSONResponse({"result": [dict(r) for r in rows.mappings()]})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/partner", methods=["POST"], auth="session")
async def create_customer(request: Request) -> JSONResponse:
    """FR-001/007/013: creates a `res.partner` flagged as a customer
    (`customer_rank=1`)."""
    env = request.app.state.env
    from dodoo.addons.account.models.account_partner import write_partner_properties
    from dodoo.addons.account.validators import CustomerCreate, validate
    from dodoo.addons.base.models.res_partner import ResPartner

    body = await request.json()
    try:
        payload = validate(CustomerCreate, body)
        vals = payload.model_dump(
            exclude={"property_payment_term_id", "property_currency_id"}, exclude_none=True
        )
        partner_id = await ResPartner.create(env, vals)
        await write_partner_properties(
            env,
            partner_id,
            {
                "customer_rank": 1,
                "property_payment_term_id": payload.property_payment_term_id,
                "property_currency_id": payload.property_currency_id,
            },
        )
        _log.info(
            "res.partner customer created",
            extra={"model": "res.partner", "record_id": partner_id, "event": "create_customer"},
        )
        return JSONResponse({"result": partner_id})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/partner/{partner_id}", methods=["GET"], auth="session")
async def read_customer(request: Request, partner_id: int) -> JSONResponse:
    """Full `res.partner` read including the account-owned raw columns
    (`customer_rank`/`property_currency_id`/`property_payment_term_id`/
    `supplier_rank`/`property_supplier_payment_term_id`) the generic
    `read`/`search_read` RPC can't return, since they aren't declared `Field`s
    on `base`'s `ResPartner` (ADR-046/049). Shared by both `customer-form.js`
    and `vendor-form.js` — a partner's role columns are read together
    regardless of which form is loading it (010-vendor-database)."""
    env = request.app.state.env

    try:
        async with env.dml_conn() as conn:
            from sqlalchemy import text

            row = await conn.execute(
                text(
                    "SELECT id, name, email, phone, street, city, state_id, zip, "
                    "country_id, vat, active, customer_rank, property_currency_id, "
                    "property_payment_term_id, supplier_rank, "
                    "property_supplier_payment_term_id "
                    "FROM res_partner WHERE id = :pid"
                ),
                {"pid": partner_id},
            )
            rec = row.mappings().fetchone()
        if not rec:
            return JSONResponse({"error": f"Partner {partner_id} does not exist"}, status_code=400)
        return JSONResponse({"result": dict(rec)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/partner/{partner_id}", methods=["PATCH"], auth="session")
async def update_customer(request: Request, partner_id: int) -> JSONResponse:
    """FR-002: partial update of a customer record."""
    env = request.app.state.env
    from dodoo.addons.account.models.account_partner import write_partner_properties
    from dodoo.addons.account.validators import CustomerUpdate, validate
    from dodoo.addons.base.models.res_partner import ResPartner

    body = await request.json()
    try:
        payload = validate(CustomerUpdate, body)
        vals = payload.model_dump(
            exclude={"property_payment_term_id", "property_currency_id"}, exclude_unset=True
        )
        if vals:
            await ResPartner.write(env, [partner_id], vals)
        raw_vals = payload.model_dump(
            include={"property_payment_term_id", "property_currency_id"}, exclude_unset=True
        )
        if raw_vals:
            await write_partner_properties(env, partner_id, raw_vals)
        _log.info(
            "res.partner customer updated",
            extra={"model": "res.partner", "record_id": partner_id, "event": "update_customer"},
        )
        return JSONResponse({"result": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/partner/{partner_id}/ar-ledger", methods=["GET"], auth="session")
async def partner_ar_ledger(request: Request, partner_id: int) -> JSONResponse:
    """FR-008/009/010/012, ADR-047: outstanding AR balance + posted invoice/
    credit-note/payment history, computed on demand."""
    env = request.app.state.env
    from dodoo.addons.account.models.account_partner import get_ar_ledger

    try:
        result = await get_ar_ledger(env, partner_id)
        _log.info(
            "res.partner AR ledger read",
            extra={"model": "res.partner", "record_id": partner_id, "event": "ar_ledger_read"},
        )
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# ---- Vendor database (010-vendor-database, FR-001/002/008/009/010) ----


@route("/account/vendors", methods=["GET"], auth="session")
async def list_vendors(request: Request) -> JSONResponse:
    """FR-003/004: vendors (`supplier_rank > 0`) for the list/search view — a
    raw route because `supplier_rank` isn't a declared `Field` on `base`'s
    `ResPartner`, so the generic `search_read` domain compiler can't filter on
    it (ADR-049)."""
    env = request.app.state.env
    include_archived = request.query_params.get("include_archived") == "true"

    try:
        async with env.dml_conn() as conn:
            from sqlalchemy import text

            active_clause = "" if include_archived else "AND active = TRUE"
            rows = await conn.execute(
                text(
                    "SELECT id, name, vat, email, phone, active, supplier_rank "
                    f"FROM res_partner WHERE supplier_rank > 0 {active_clause} "  # noqa: S608
                    "ORDER BY name"
                )
            )
            return JSONResponse({"result": [dict(r) for r in rows.mappings()]})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/vendor", methods=["POST"], auth="session")
async def create_vendor(request: Request) -> JSONResponse:
    """FR-001/007/013: creates a `res.partner` flagged as a vendor
    (`supplier_rank=1`). A distinct path from `POST /account/partner`
    (customer create) since that route is fixed to `CustomerCreate`, which
    would reject a vendor-shaped payload's `supplier_rank`/
    `property_supplier_payment_term_id` fields (ADR-051)."""
    env = request.app.state.env
    from dodoo.addons.account.models.account_partner import write_partner_properties
    from dodoo.addons.account.validators import VendorCreate, validate
    from dodoo.addons.base.models.res_partner import ResPartner

    body = await request.json()
    try:
        payload = validate(VendorCreate, body)
        vals = payload.model_dump(
            exclude={"property_supplier_payment_term_id", "property_currency_id"},
            exclude_none=True,
        )
        partner_id = await ResPartner.create(env, vals)
        await write_partner_properties(
            env,
            partner_id,
            {
                "supplier_rank": 1,
                "property_supplier_payment_term_id": payload.property_supplier_payment_term_id,
                "property_currency_id": payload.property_currency_id,
            },
        )
        _log.info(
            "res.partner vendor created",
            extra={"model": "res.partner", "record_id": partner_id, "event": "create_vendor"},
        )
        return JSONResponse({"result": partner_id})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/vendor/{partner_id}", methods=["PATCH"], auth="session")
async def update_vendor(request: Request, partner_id: int) -> JSONResponse:
    """FR-002: partial update of a vendor record. A distinct path from
    `PATCH /account/partner/{id}` (customer update) for the same reason as
    `POST /account/vendor` above (ADR-051)."""
    env = request.app.state.env
    from dodoo.addons.account.models.account_partner import write_partner_properties
    from dodoo.addons.account.validators import VendorUpdate, validate
    from dodoo.addons.base.models.res_partner import ResPartner

    body = await request.json()
    try:
        payload = validate(VendorUpdate, body)
        vals = payload.model_dump(
            exclude={"property_supplier_payment_term_id", "property_currency_id"},
            exclude_unset=True,
        )
        if vals:
            await ResPartner.write(env, [partner_id], vals)
        raw_vals = payload.model_dump(
            include={"property_supplier_payment_term_id", "property_currency_id"},
            exclude_unset=True,
        )
        if raw_vals:
            await write_partner_properties(env, partner_id, raw_vals)
        _log.info(
            "res.partner vendor updated",
            extra={"model": "res.partner", "record_id": partner_id, "event": "update_vendor"},
        )
        return JSONResponse({"result": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@route("/account/partner/{partner_id}/ap-ledger", methods=["GET"], auth="session")
async def partner_ap_ledger(request: Request, partner_id: int) -> JSONResponse:
    """FR-008/009/010/012, ADR-050: outstanding AP balance + posted bill/
    credit-note/payment history, computed on demand."""
    env = request.app.state.env
    from dodoo.addons.account.models.account_partner import get_ap_ledger

    try:
        result = await get_ap_ledger(env, partner_id)
        _log.info(
            "res.partner AP ledger read",
            extra={"model": "res.partner", "record_id": partner_id, "event": "ap_ledger_read"},
        )
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
