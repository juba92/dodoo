from __future__ import annotations

import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from dodoo.core.fields import (
    Boolean,
    Char,
    Integer,
    Many2one,
    Monetary,
    Selection,
    Text,
)
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

PAYMENT_TERM_VALUE_CHOICES = [
    ("percent", "Percent"),
    ("fixed", "Fixed"),
]

DELAY_TYPE_CHOICES = [
    ("days_after", "Days After Invoice Date"),
    ("days_after_end_of_month", "Days After End of Month"),
    ("days_after_end_of_next_month", "Days After End of Next Month"),
    ("days_end_of_month_on_the", "Day of Month"),
]


def _end_of_month(d: datetime.date) -> datetime.date:
    import calendar

    last_day = calendar.monthrange(d.year, d.month)[1]
    return d.replace(day=last_day)


def _next_month_end(d: datetime.date) -> datetime.date:
    import calendar

    if d.month == 12:
        first_next = datetime.date(d.year + 1, 1, 1)
    else:
        first_next = datetime.date(d.year, d.month + 1, 1)
    last_day = calendar.monthrange(first_next.year, first_next.month)[1]
    return first_next.replace(day=last_day)


def _compute_due_date(
    invoice_date: datetime.date, delay_type: str, nb_days: int
) -> datetime.date:
    if delay_type == "days_after":
        return invoice_date + datetime.timedelta(days=nb_days)
    if delay_type == "days_after_end_of_month":
        return _end_of_month(invoice_date) + datetime.timedelta(days=nb_days)
    if delay_type == "days_after_end_of_next_month":
        return _next_month_end(invoice_date) + datetime.timedelta(days=nb_days)
    if delay_type == "days_end_of_month_on_the":
        eom = _end_of_month(invoice_date)
        return eom.replace(day=min(nb_days, eom.day))
    return invoice_date + datetime.timedelta(days=nb_days)


class AccountPaymentTerm(BaseModel):
    _name = "account.payment.term"

    name = Char(size=256, required=True)
    note = Text()
    early_discount = Boolean(default=False)
    discount_percentage = Monetary()
    discount_days = Integer(default=0)
    company_id = Many2one("res.company", required=True)
    active = Boolean(default=True)

    @classmethod
    async def compute_installments(
        cls,
        env: Environment,
        payment_term_id: int,
        invoice_date: datetime.date,
        amount_total: Decimal,
    ) -> list[dict]:
        """Return list of {due_date, amount} installments."""
        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT sequence, value, value_amount, delay_type, nb_days "
                    "FROM account_payment_term_line "
                    "WHERE payment_term_id=:tid ORDER BY sequence"
                ),
                {"tid": payment_term_id},
            )
            term_lines = [dict(row._mapping) for row in rows]

        if not term_lines:
            return [{"due_date": invoice_date, "amount": amount_total}]

        installments = []
        remaining = amount_total
        for i, tl in enumerate(term_lines):
            due_date = _compute_due_date(
                invoice_date,
                tl["delay_type"] or "days_after",
                int(tl["nb_days"] or 0),
            )
            is_last = i == len(term_lines) - 1
            if is_last or tl["value"] == "fixed":
                inst_amount = (
                    remaining if is_last else Decimal(str(tl["value_amount"] or "0"))
                )
            else:
                inst_amount = (
                    amount_total
                    * Decimal(str(tl["value_amount"] or "0"))
                    / Decimal("100")
                )
                inst_amount = inst_amount.quantize(Decimal("0.01"))
            installments.append({"due_date": due_date, "amount": inst_amount})
            if not is_last:
                remaining -= inst_amount

        return installments


class AccountPaymentTermLine(BaseModel):
    _name = "account.payment.term.line"

    payment_term_id = Many2one("account.payment.term", required=True)
    sequence = Integer(default=10)
    value = Selection(PAYMENT_TERM_VALUE_CHOICES)
    value_amount = Monetary()
    delay_type = Selection(DELAY_TYPE_CHOICES)
    nb_days = Integer(default=0)
