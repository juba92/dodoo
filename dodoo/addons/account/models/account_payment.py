from __future__ import annotations

import datetime
import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Char, Date, Many2one, Monetary, Selection
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)

PAYMENT_TYPE_CHOICES = [
    ("inbound", "Inbound"),
    ("outbound", "Outbound"),
]

PARTNER_TYPE_CHOICES = [
    ("customer", "Customer"),
    ("supplier", "Supplier"),
]

STATE_CHOICES = [
    ("draft", "Draft"),
    ("posted", "Posted"),
    ("cancelled", "Cancelled"),
]

_CASH_BANK = frozenset({"cash", "bank"})


class AccountPayment(BaseModel):
    _name = "account.payment"

    name = Char(size=64)
    payment_type = Selection(PAYMENT_TYPE_CHOICES, required=True)
    partner_type = Selection(PARTNER_TYPE_CHOICES, required=True)
    partner_id = Many2one("res.partner", required=True)
    journal_id = Many2one("account.journal", required=True)
    currency_id = Many2one("res.currency", required=True)
    amount = Monetary()
    date = Date(required=True)
    ref = Char(size=256)
    state = Selection(STATE_CHOICES, default="draft")
    move_id = Many2one("account.move")
    company_id = Many2one("res.company", required=True)

    @classmethod
    async def action_post(cls, env: Environment, ids: list[int]) -> bool:
        """Create and post the accounting journal entry for the payment."""
        from dodoo.addons.account.models.account_move import AccountMove
        from dodoo.addons.account.models.account_sequence import get_next_sequence

        for payment_id in ids:
            records = await super().read(
                env,
                [payment_id],
                [
                    "state",
                    "payment_type",
                    "partner_type",
                    "partner_id",
                    "journal_id",
                    "currency_id",
                    "amount",
                    "date",
                    "company_id",
                    "ref",
                ],
            )
            if not records:
                raise DodooError(f"account.payment {payment_id} not found")
            rec = records[0]

            if rec["state"] != "draft":
                raise DodooError(f"Payment {payment_id} is not in draft state")

            amount = Decimal(str(rec["amount"] or "0"))
            if amount <= 0:
                raise DodooError(f"Payment {payment_id}: amount must be positive")

            # Validate journal type
            async with env.dml_conn() as conn:
                jrow = await conn.execute(
                    text(
                        "SELECT type, default_account_id FROM account_journal WHERE id=:jid"
                    ),
                    {"jid": rec["journal_id"]},
                )
                journal = jrow.fetchone()
                if not journal or journal[0] not in _CASH_BANK:
                    raise DodooError(
                        f"Payment journal must be cash or bank, got: {journal[0] if journal else None}"
                    )
                bank_account_id = journal[1]

            if not bank_account_id:
                raise DodooError(
                    f"Payment journal {rec['journal_id']} has no default account"
                )

            # Determine AR/AP account from partner
            async with env.dml_conn() as conn:
                if rec["partner_type"] == "customer":
                    prow = await conn.execute(
                        text(
                            "SELECT property_account_receivable_id FROM res_partner WHERE id=:pid"
                        ),
                        {"pid": rec["partner_id"]},
                    )
                else:
                    prow = await conn.execute(
                        text(
                            "SELECT property_account_payable_id FROM res_partner WHERE id=:pid"
                        ),
                        {"pid": rec["partner_id"]},
                    )
                prow_data = prow.fetchone()
                ar_ap_account_id = prow_data[0] if prow_data else None

            if not ar_ap_account_id:
                # Fall back to first AR/AP account for the company
                async with env.dml_conn() as conn:
                    acct_type = (
                        "asset_receivable"
                        if rec["partner_type"] == "customer"
                        else "liability_payable"
                    )
                    arow = await conn.execute(
                        text(
                            "SELECT id FROM account_account "
                            "WHERE account_type=:atype AND company_id=:cid LIMIT 1"
                        ),
                        {"atype": acct_type, "cid": rec["company_id"]},
                    )
                    arow_data = arow.fetchone()
                    ar_ap_account_id = arow_data[0] if arow_data else None

            if not ar_ap_account_id:
                raise DodooError("No AR/AP account found for payment")

            pay_date = rec["date"] or datetime.date.today()

            # Build debit/credit lines
            # inbound customer: Dr Bank / Cr AR
            # outbound vendor:  Dr AP  / Cr Bank
            if rec["payment_type"] == "inbound":
                line1 = {
                    "account_id": bank_account_id,
                    "debit": amount,
                    "credit": Decimal("0"),
                }
                line2 = {
                    "account_id": ar_ap_account_id,
                    "debit": Decimal("0"),
                    "credit": amount,
                }
            else:
                line1 = {
                    "account_id": ar_ap_account_id,
                    "debit": amount,
                    "credit": Decimal("0"),
                }
                line2 = {
                    "account_id": bank_account_id,
                    "debit": Decimal("0"),
                    "credit": amount,
                }

            move_id = await AccountMove.create(
                env,
                {
                    "move_type": "entry",
                    "journal_id": rec["journal_id"],
                    "company_id": rec["company_id"],
                    "currency_id": rec["currency_id"],
                    "partner_id": rec.get("partner_id"),
                    "date": pay_date,
                    "ref": rec.get("ref"),
                    "state": "draft",
                },
            )

            async with env.dml_conn() as conn:
                for line in [line1, line2]:
                    bal = line["debit"] - line["credit"]
                    await conn.execute(
                        text(
                            "INSERT INTO account_move_line "
                            "(move_id, account_id, partner_id, date, display_type, "
                            "debit, credit, balance, amount_residual, create_date, write_date) "
                            "VALUES (:mid, :acct, :pid, :dt, 'payment_term', "
                            ":debit, :credit, :bal, :residual, now(), now())"
                        ),
                        {
                            "mid": move_id,
                            "acct": line["account_id"],
                            "pid": rec.get("partner_id"),
                            "dt": pay_date,
                            "debit": str(line["debit"]),
                            "credit": str(line["credit"]),
                            "bal": str(bal),
                            "residual": str(bal),
                        },
                    )
                await conn.commit()

            await AccountMove.action_post(env, [move_id])

            # Assign PAY sequence name
            async with env.dml_conn() as conn:
                seq_no = await get_next_sequence(conn, "PAY", pay_date.year)
                pay_name = f"PAY/{pay_date.year}/{seq_no:04d}"
                await conn.execute(
                    text(
                        "UPDATE account_payment SET "
                        "state='posted', move_id=:mid, name=:name, write_date=now() "
                        "WHERE id=:pid"
                    ),
                    {"mid": move_id, "name": pay_name, "pid": payment_id},
                )
                await conn.commit()

            _log.info(
                "account.payment posted",
                extra={
                    "model": "account.payment",
                    "record_id": payment_id,
                    "pay_name": pay_name,
                    "event": "action_post",
                    "move_id": move_id,
                },
            )

        return True

    @classmethod
    async def register_against_invoices(
        cls,
        env: Environment,
        payment_id: int,
        invoice_ids: list[int],
    ) -> dict:
        """Reconcile payment AR/AP line against invoice AR/AP lines."""
        from dodoo.addons.account.models.account_move import AccountMove
        from dodoo.addons.account.models.account_reconcile import (
            AccountPartialReconcile,
        )

        records = await super().read(
            env, [payment_id], ["state", "move_id", "payment_type"]
        )
        if not records or records[0]["state"] != "posted":
            raise DodooError(f"Payment {payment_id} must be posted before reconciling")
        rec = records[0]

        pay_move_id = rec["move_id"]
        if not pay_move_id:
            raise DodooError(f"Payment {payment_id} has no linked journal entry")

        # Get payment AR/AP line (must be on a reconcilable account)
        async with env.dml_conn() as conn:
            prow = await conn.execute(
                text(
                    "SELECT ml.id, ml.amount_residual FROM account_move_line ml "
                    "JOIN account_account a ON a.id = ml.account_id "
                    "WHERE ml.move_id=:mid AND ml.display_type='payment_term' "
                    "AND a.reconcile=TRUE LIMIT 1"
                ),
                {"mid": pay_move_id},
            )
            pline = prow.fetchone()

        if not pline:
            raise DodooError("Payment has no reconcilable AR/AP line")

        pay_line_id = pline[0]
        results = []

        for inv_id in invoice_ids:
            inv_records = await AccountMove.read(env, [inv_id], ["state", "move_type"])
            if not inv_records or inv_records[0]["state"] != "posted":
                continue

            async with env.dml_conn() as conn:
                irow = await conn.execute(
                    text(
                        "SELECT ml.id, ml.amount_residual FROM account_move_line ml "
                        "JOIN account_account a ON a.id = ml.account_id "
                        "WHERE ml.move_id=:mid AND ml.display_type='payment_term' "
                        "AND a.reconcile=TRUE LIMIT 1"
                    ),
                    {"mid": inv_id},
                )
                iline = irow.fetchone()

            if not iline:
                continue

            inv_line_id = iline[0]
            pay_residual = abs(Decimal(str(pline[1] or "0")))
            inv_residual = abs(Decimal(str(iline[1] or "0")))
            rec_amount = min(pay_residual, inv_residual)

            if rec_amount <= 0:
                continue

            # Inbound: invoice AR is debit (positive balance), payment AR is credit (negative)
            # Outbound: payment AP is debit (positive balance), invoice AP is credit (negative)
            if rec["payment_type"] == "inbound":
                result = await AccountPartialReconcile.reconcile_lines(
                    env, inv_line_id, pay_line_id, rec_amount
                )
            else:
                result = await AccountPartialReconcile.reconcile_lines(
                    env, pay_line_id, inv_line_id, rec_amount
                )
            results.append({"invoice_id": inv_id, **result})

            # Update payment_state and amount_residual on invoice
            new_pstate = await AccountMove._compute_payment_state(env, inv_id)
            async with env.dml_conn() as conn:
                res_row = await conn.execute(
                    text(
                        "SELECT ROUND(ABS(SUM(amount_residual))::NUMERIC, 2) "
                        "FROM account_move_line "
                        "WHERE move_id=:mid AND display_type='payment_term'"
                    ),
                    {"mid": inv_id},
                )
                new_residual = res_row.scalar_one() or 0
                await conn.execute(
                    text(
                        "UPDATE account_move SET payment_state=:ps, "
                        "amount_residual=:residual, write_date=now() WHERE id=:id"
                    ),
                    {"ps": new_pstate, "residual": str(new_residual), "id": inv_id},
                )
                await conn.commit()

        return {"reconciled": results}
