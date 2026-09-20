"""009-customer-database / 010-vendor-database: accounting-owned partner fields
and the AR/AP ledgers.

``res.partner`` lives in ``base``, which declares only the general contact fields
(``name``/``email``/``phone``/``vat``/billing address). ``customer_rank``/
``supplier_rank`` and ``property_currency_id`` are ``account``-owned raw columns
(ADR-046/049, the same cross-addon idiom already used for
``property_account_receivable_id``/``property_account_payable_id``/
``property_payment_term_id``/``property_supplier_payment_term_id``) — not
declared ``Field``s on ``base``'s ``ResPartner`` class, so the generic
``ResPartner.create``/``write`` silently drops them. This module is where
``account`` reads and writes its own columns.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.core.exceptions import DodooError

if TYPE_CHECKING:
    from dodoo import Environment

_PROPERTY_COLUMNS = (
    "customer_rank",
    "property_currency_id",
    "property_payment_term_id",
    # 010-vendor-database, data-model.md
    "supplier_rank",
    "property_supplier_payment_term_id",
)

# FR-008/009: which account.move.move_type values represent AR-affecting customer
# documents — the same set account_move.py's own `_SALE_TYPES` uses.
_AR_MOVE_TYPES = ("out_invoice", "out_refund", "out_receipt")

# 010-vendor-database FR-008/009: which account.move.move_type values represent
# AP-affecting vendor documents — the same set account_move.py's own
# `_PURCHASE_TYPES` uses.
_AP_MOVE_TYPES = ("in_invoice", "in_refund", "in_receipt")

# account.move.payment_state -> AR-ledger line status (FR-009/012). "reversed"
# is included defensively (it's one of PAYMENT_STATE_CHOICES) even though no
# code path in this addon currently sets it — `action_reverse` does not
# reconcile the original against its reversal, so voiding a *posted* invoice
# today only zeroes it out once the reversal is manually reconciled against
# it like any other AR line; a *draft* invoice cancelled via `action_cancel`
# (ADR-038 — the only `state='cancel'` path that exists) is handled
# separately below, since it never gets a `payment_term` line at all.
_PAYMENT_STATE_TO_STATUS = {
    "not_paid": "open",
    "blocked": "open",
    "reversed": "cancelled",
    "partial": "partial",
    "in_payment": "paid",
    "paid": "paid",
}


async def write_partner_properties(
    env: Environment, partner_id: int, vals: dict[str, Any]
) -> None:
    """Raw ``UPDATE`` for whichever of ``_PROPERTY_COLUMNS`` are present in
    ``vals`` (partial update — absent keys are left untouched)."""
    cols = [c for c in _PROPERTY_COLUMNS if c in vals]
    if not cols:
        return
    set_clause = ", ".join(f"{c} = :{c}" for c in cols)
    params: dict[str, Any] = {c: vals[c] for c in cols}
    params["pid"] = partner_id
    async with env.dml_conn() as conn:
        await conn.execute(
            text(f"UPDATE res_partner SET {set_clause} WHERE id = :pid"),  # noqa: S608
            params,
        )
        await conn.commit()


def _status_and_balance(
    lines: list[dict[str, Any]],
) -> tuple[Decimal, list[dict[str, Any]]]:
    """ADR-047: pure, no-DB balance/status computation (Principle II — unit
    tested without Postgres). ``lines`` are plain dicts already fetched from
    ``account_move``/``account_payment``; each carries ``amount_residual``
    (0 for a payment line, which never has an open residual of its own) and a
    ``_raw_status`` the caller has already resolved to one of "open"/
    "partial"/"paid"/"cancelled".

    Cancelled documents are excluded from the balance but kept in the
    returned list with ``status: "cancelled"`` (FR-012).
    """
    balance = Decimal("0")
    out_lines: list[dict[str, Any]] = []
    for line in lines:
        status = line["_raw_status"]
        if status != "cancelled":
            balance += Decimal(str(line["amount_residual"] or "0"))
        out_lines.append(
            {
                "date": line["date"],
                "type": line["type"],
                "move_id": line["move_id"],
                "reference": line["reference"],
                "amount": str(Decimal(str(line["amount"] or "0"))),
                "status": status,
            }
        )
    out_lines.sort(key=lambda entry: entry["date"])
    return balance, out_lines


async def get_ar_ledger(env: Environment, partner_id: int) -> dict[str, Any]:
    """FR-008/009/010/012, ADR-047: a customer's outstanding AR balance and
    posted invoice/credit-note/payment history, computed on demand — never a
    stored/maintained field. Raises ``DodooError`` for an unknown partner."""
    async with env.dml_conn() as conn:
        prow = await conn.execute(
            text("SELECT id, property_currency_id, company_id FROM res_partner WHERE id = :pid"),
            {"pid": partner_id},
        )
        partner = prow.fetchone()
        if not partner:
            raise DodooError(f"Partner {partner_id} does not exist")
        currency_id = partner.property_currency_id
        if not currency_id and partner.company_id:
            crow = await conn.execute(
                text("SELECT currency_id FROM res_company WHERE id = :cid"),
                {"cid": partner.company_id},
            )
            company = crow.fetchone()
            currency_id = company.currency_id if company else None

        # The move's own `amount_residual` is always a positive face-value
        # magnitude (account_move.py posts it as `total`, regardless of
        # move_type); the *signed* AR effect — what actually nets a credit
        # note against an invoice — lives on the payment_term line's own
        # `amount_residual`, exactly like AccountReportAgedReceivable's
        # already-proven `_aged_report` query reads it. Only `posted` moves
        # are expected to carry that line (`_compute_payment_term_lines` only
        # runs at `action_post`), so this query is scoped to `state='posted'`.
        move_rows = await conn.execute(
            text(
                "SELECT m.date, m.move_type, m.id AS move_id, m.name AS reference, "
                "m.amount_total AS amount, "
                "COALESCE(ml.amount_residual, 0) AS amount_residual, "
                "m.payment_state "
                "FROM account_move m "
                "JOIN account_move_line ml ON ml.move_id = m.id "
                "  AND ml.display_type = 'payment_term' "
                "JOIN account_account a ON a.id = ml.account_id "
                "  AND a.account_type = 'asset_receivable' "
                "WHERE m.partner_id = :pid AND m.move_type = ANY(:types) AND m.state = 'posted'"
            ),
            {"pid": partner_id, "types": list(_AR_MOVE_TYPES)},
        )
        lines: list[dict[str, Any]] = []
        for r in move_rows.mappings():
            status = _PAYMENT_STATE_TO_STATUS.get(r["payment_state"], "open")
            lines.append(
                {
                    "date": r["date"],
                    "type": "credit_note" if r["move_type"] == "out_refund" else "invoice",
                    "move_id": r["move_id"],
                    "reference": r["reference"],
                    "amount": r["amount"],
                    "amount_residual": 0 if status == "cancelled" else r["amount_residual"],
                    "_raw_status": status,
                }
            )

        # FR-012/Edge Cases: a move cancelled before ever being posted
        # (`action_cancel` only accepts `draft` moves, ADR-038) never gets a
        # `payment_term` line at all (`_compute_payment_term_lines` only runs
        # at `action_post`) — listed separately so it still appears in
        # history with a "cancelled" status and zero balance contribution.
        cancelled_rows = await conn.execute(
            text(
                "SELECT date, move_type, id AS move_id, name AS reference, "
                "amount_total AS amount "
                "FROM account_move "
                "WHERE partner_id = :pid AND move_type = ANY(:types) AND state = 'cancel'"
            ),
            {"pid": partner_id, "types": list(_AR_MOVE_TYPES)},
        )
        for r in cancelled_rows.mappings():
            lines.append(
                {
                    "date": r["date"],
                    "type": "credit_note" if r["move_type"] == "out_refund" else "invoice",
                    "move_id": r["move_id"],
                    "reference": r["reference"],
                    "amount": r["amount"],
                    "amount_residual": 0,
                    "_raw_status": "cancelled",
                }
            )

        payment_rows = await conn.execute(
            text(
                "SELECT date, id AS move_id, name AS reference, amount, state "
                "FROM account_payment "
                "WHERE partner_id = :pid AND partner_type = 'customer' AND state != 'draft'"
            ),
            {"pid": partner_id},
        )
        for r in payment_rows.mappings():
            status = "cancelled" if r["state"] == "cancel" else "paid"
            lines.append(
                {
                    "date": r["date"],
                    "type": "payment",
                    "move_id": r["move_id"],
                    "reference": r["reference"],
                    "amount": r["amount"],
                    "amount_residual": 0,
                    "_raw_status": status,
                }
            )

    balance, out_lines = _status_and_balance(lines)
    return {
        "balance": str(balance),
        "currency_id": currency_id,
        "lines": [
            {
                "date": entry["date"].isoformat()
                if hasattr(entry["date"], "isoformat")
                else entry["date"],
                "type": entry["type"],
                "move_id": entry["move_id"],
                "reference": entry["reference"],
                "amount": entry["amount"],
                "status": entry["status"],
            }
            for entry in out_lines
        ],
    }


async def get_ap_ledger(env: Environment, partner_id: int) -> dict[str, Any]:
    """FR-008/009/010/012, ADR-050: a vendor's outstanding AP balance and
    posted bill/credit-note/payment history, computed on demand — never a
    stored/maintained field. Raises ``DodooError`` for an unknown partner.

    Mirrors ``get_ar_ledger`` exactly, substituting ``_AP_MOVE_TYPES``/
    ``liability_payable``/``partner_type='supplier'`` for their AR
    counterparts, and reuses ``_status_and_balance`` unmodified (research.md
    D5) — that helper has no AR-specific assumption in its body."""
    async with env.dml_conn() as conn:
        prow = await conn.execute(
            text("SELECT id, property_currency_id, company_id FROM res_partner WHERE id = :pid"),
            {"pid": partner_id},
        )
        partner = prow.fetchone()
        if not partner:
            raise DodooError(f"Partner {partner_id} does not exist")
        currency_id = partner.property_currency_id
        if not currency_id and partner.company_id:
            crow = await conn.execute(
                text("SELECT currency_id FROM res_company WHERE id = :cid"),
                {"cid": partner.company_id},
            )
            company = crow.fetchone()
            currency_id = company.currency_id if company else None

        move_rows = await conn.execute(
            text(
                "SELECT m.date, m.move_type, m.id AS move_id, m.name AS reference, "
                "m.amount_total AS amount, "
                "COALESCE(ml.amount_residual, 0) AS amount_residual, "
                "m.payment_state "
                "FROM account_move m "
                "JOIN account_move_line ml ON ml.move_id = m.id "
                "  AND ml.display_type = 'payment_term' "
                "JOIN account_account a ON a.id = ml.account_id "
                "  AND a.account_type = 'liability_payable' "
                "WHERE m.partner_id = :pid AND m.move_type = ANY(:types) AND m.state = 'posted'"
            ),
            {"pid": partner_id, "types": list(_AP_MOVE_TYPES)},
        )
        lines: list[dict[str, Any]] = []
        for r in move_rows.mappings():
            status = _PAYMENT_STATE_TO_STATUS.get(r["payment_state"], "open")
            lines.append(
                {
                    "date": r["date"],
                    "type": "credit_note" if r["move_type"] == "in_refund" else "bill",
                    "move_id": r["move_id"],
                    "reference": r["reference"],
                    "amount": r["amount"],
                    "amount_residual": 0 if status == "cancelled" else r["amount_residual"],
                    "_raw_status": status,
                }
            )

        # FR-012/Edge Cases: a move cancelled before ever being posted
        # (`action_cancel` only accepts `draft` moves, ADR-038) never gets a
        # `payment_term` line at all — listed separately so it still appears
        # in history with a "cancelled" status and zero balance contribution.
        cancelled_rows = await conn.execute(
            text(
                "SELECT date, move_type, id AS move_id, name AS reference, "
                "amount_total AS amount "
                "FROM account_move "
                "WHERE partner_id = :pid AND move_type = ANY(:types) AND state = 'cancel'"
            ),
            {"pid": partner_id, "types": list(_AP_MOVE_TYPES)},
        )
        for r in cancelled_rows.mappings():
            lines.append(
                {
                    "date": r["date"],
                    "type": "credit_note" if r["move_type"] == "in_refund" else "bill",
                    "move_id": r["move_id"],
                    "reference": r["reference"],
                    "amount": r["amount"],
                    "amount_residual": 0,
                    "_raw_status": "cancelled",
                }
            )

        payment_rows = await conn.execute(
            text(
                "SELECT date, id AS move_id, name AS reference, amount, state "
                "FROM account_payment "
                "WHERE partner_id = :pid AND partner_type = 'supplier' AND state != 'draft'"
            ),
            {"pid": partner_id},
        )
        for r in payment_rows.mappings():
            status = "cancelled" if r["state"] == "cancel" else "paid"
            lines.append(
                {
                    "date": r["date"],
                    "type": "payment",
                    "move_id": r["move_id"],
                    "reference": r["reference"],
                    "amount": r["amount"],
                    "amount_residual": 0,
                    "_raw_status": status,
                }
            )

    balance, out_lines = _status_and_balance(lines)
    return {
        "balance": str(balance),
        "currency_id": currency_id,
        "lines": [
            {
                "date": entry["date"].isoformat()
                if hasattr(entry["date"], "isoformat")
                else entry["date"],
                "type": entry["type"],
                "move_id": entry["move_id"],
                "reference": entry["reference"],
                "amount": entry["amount"],
                "status": entry["status"],
            }
            for entry in out_lines
        ],
    }
