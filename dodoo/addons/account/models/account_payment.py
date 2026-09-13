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
                        "SELECT type, default_account_id, code FROM account_journal WHERE id=:jid"
                    ),
                    {"jid": rec["journal_id"]},
                )
                journal = jrow.fetchone()
                if not journal or journal[0] not in _CASH_BANK:
                    raise DodooError(
                        f"Payment journal must be cash or bank, got: {journal[0] if journal else None}"
                    )
                bank_account_id = journal[1]
                # FR-003, ADR-038: the payment's own display-name prefix is also
                # the posting journal's own code, not a static "PAY" constant.
                journal_code = journal[2] or "PAY"

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

            # Assign sequence name (journal-scoped, FR-003)
            async with env.dml_conn() as conn:
                seq_no = await get_next_sequence(conn, journal_code, pay_date.year)
                pay_name = f"{journal_code}/{pay_date.year}/{seq_no:04d}"
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
    async def _apply_early_discount(
        cls,
        env: Environment,
        inv_id: int,
        inv_line_id: int,
        inv_residual: Decimal,
        payment_date,
        company_id: int,
    ) -> Decimal:
        """FR-018: if the invoice's payment term has an active early-payment
        discount and ``payment_date`` falls on/before the discount window, post
        the discount taken to ``early_payment_discount_account_id`` and
        immediately reconcile it against the invoice's AR/AP line, then return
        the *reduced* residual the actual cash payment still needs to cover.

        Returns ``inv_residual`` unchanged when no discount applies.
        """
        from dodoo.addons.account.models.account_move import AccountMove
        from dodoo.addons.account.models.account_reconcile import (
            AccountPartialReconcile,
        )

        inv_records = await AccountMove.read(
            env, [inv_id], ["invoice_payment_term_id", "invoice_date", "date", "currency_id"]
        )
        if not inv_records or not inv_records[0].get("invoice_payment_term_id"):
            return inv_residual
        inv_rec = inv_records[0]

        async with env.dml_conn() as conn:
            term_row = await conn.execute(
                text(
                    "SELECT early_discount, discount_percentage, discount_days, "
                    "       early_payment_discount_account_id "
                    "FROM account_payment_term WHERE id=:tid"
                ),
                {"tid": inv_rec["invoice_payment_term_id"]},
            )
            term = term_row.fetchone()

        if not term or not term[0]:
            return inv_residual

        discount_pct = Decimal(str(term[1] or "0"))
        discount_days = int(term[2] or 0)
        discount_account_id = term[3]
        if not discount_account_id or discount_pct <= 0:
            return inv_residual

        base_date = inv_rec.get("invoice_date") or inv_rec.get("date")
        if isinstance(base_date, str):
            base_date = datetime.date.fromisoformat(base_date)
        if isinstance(payment_date, str):
            payment_date = datetime.date.fromisoformat(payment_date)
        discount_date = base_date + datetime.timedelta(days=discount_days)
        if payment_date > discount_date:
            return inv_residual  # outside the discount window

        discount_amount = (inv_residual * discount_pct / Decimal("100")).quantize(Decimal("0.01"))
        if discount_amount <= 0:
            return inv_residual

        # Determine the invoice line's account and sign to balance the discount
        # move against (mirrors the invoice's own AR/AP account).
        async with env.dml_conn() as conn:
            iarow = await conn.execute(
                text("SELECT account_id, debit, credit FROM account_move_line WHERE id=:lid"),
                {"lid": inv_line_id},
            )
            iaccount = iarow.fetchone()
        if not iaccount:
            return inv_residual
        ar_ap_account_id, i_debit, i_credit = iaccount
        # invoice AR line is a debit (asset_receivable); AP line is a credit —
        # the discount move must move the *opposite* side to close the residual.
        is_ar = Decimal(str(i_debit)) >= Decimal(str(i_credit))

        discount_move_id = await AccountMove.create(
            env,
            {
                "move_type": "entry",
                "journal_id": (await cls._misc_journal_id(env, company_id)),
                "company_id": company_id,
                "currency_id": inv_rec.get("currency_id") or None,
                "date": payment_date,
                "ref": f"Early payment discount for invoice {inv_id}",
                "state": "draft",
            },
        )
        async with env.dml_conn() as conn:
            # Line 1: closes the invoice's AR/AP residual (opposite side of the invoice line)
            d1, c1 = (Decimal("0"), discount_amount) if is_ar else (discount_amount, Decimal("0"))
            await conn.execute(
                text(
                    "INSERT INTO account_move_line "
                    "(move_id, account_id, date, display_type, debit, credit, balance, "
                    "amount_residual, create_date, write_date) "
                    "VALUES (:mid, :acct, :dt, 'payment_term', :d, :c, :bal, :bal, now(), now())"
                ),
                {
                    "mid": discount_move_id,
                    "acct": ar_ap_account_id,
                    "dt": payment_date,
                    "d": str(d1),
                    "c": str(c1),
                    "bal": str(d1 - c1),
                },
            )
            # Line 2: the discount expense/income (opposite side of line 1)
            d2, c2 = (discount_amount, Decimal("0")) if is_ar else (Decimal("0"), discount_amount)
            await conn.execute(
                text(
                    "INSERT INTO account_move_line "
                    "(move_id, account_id, date, display_type, debit, credit, balance, "
                    "create_date, write_date) "
                    "VALUES (:mid, :acct, :dt, 'product', :d, :c, :bal, now(), now())"
                ),
                {
                    "mid": discount_move_id,
                    "acct": discount_account_id,
                    "dt": payment_date,
                    "d": str(d2),
                    "c": str(c2),
                    "bal": str(d2 - c2),
                },
            )
            await conn.commit()

        await AccountMove.action_post(env, [discount_move_id])

        async with env.dml_conn() as conn:
            drow = await conn.execute(
                text(
                    "SELECT id FROM account_move_line WHERE move_id=:mid "
                    "AND display_type='payment_term' LIMIT 1"
                ),
                {"mid": discount_move_id},
            )
            discount_line_id = drow.scalar_one()

        if is_ar:
            await AccountPartialReconcile.reconcile_lines(
                env, inv_line_id, discount_line_id, discount_amount
            )
        else:
            await AccountPartialReconcile.reconcile_lines(
                env, discount_line_id, inv_line_id, discount_amount
            )

        return inv_residual - discount_amount

    @classmethod
    async def _misc_journal_id(cls, env: Environment, company_id: int) -> int:
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT id FROM account_journal WHERE type='general' "
                    "AND company_id=:cid LIMIT 1"
                ),
                {"cid": company_id},
            )
            return row.scalar_one()

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
            env, [payment_id], ["state", "move_id", "payment_type", "date", "company_id"]
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

            inv_residual = await cls._apply_early_discount(
                env, inv_id, inv_line_id, inv_residual, rec["date"], rec["company_id"]
            )

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
