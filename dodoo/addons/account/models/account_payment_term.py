from __future__ import annotations

import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.core.exceptions import DodooError
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
    invoice_date: datetime.date,
    delay_type: str,
    nb_days: int,
    next_month: bool = False,
) -> datetime.date:
    if delay_type == "days_after":
        return invoice_date + datetime.timedelta(days=nb_days)
    if delay_type == "days_after_end_of_month":
        return _end_of_month(invoice_date) + datetime.timedelta(days=nb_days)
    if delay_type == "days_after_end_of_next_month":
        return _next_month_end(invoice_date) + datetime.timedelta(days=nb_days)
    if delay_type == "days_end_of_month_on_the":
        # FR-019: resolve the *target month* first (the invoice date's own month,
        # or the next month when `next_month` is set), then clamp the configured
        # day within that resolved month's length — not always the invoice date's
        # own month-end.
        target_eom = _next_month_end(invoice_date) if next_month else _end_of_month(invoice_date)
        target_month_start = target_eom.replace(day=1)
        return target_month_start.replace(day=min(nb_days, target_eom.day))
    return invoice_date + datetime.timedelta(days=nb_days)


class AccountPaymentTerm(BaseModel):
    _name = "account.payment.term"

    name = Char(size=256, required=True)
    note = Text()
    early_discount = Boolean(default=False)
    discount_percentage = Monetary()
    discount_days = Integer(default=0)
    early_payment_discount_account_id = Many2one("account.account")
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
        """Return list of {due_date, amount[, discount_date, discount_amount]} installments.

        The two discount keys (FR-018) are present only when the parent term's
        ``early_discount`` is ``True``.
        """
        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT sequence, value, value_amount, delay_type, nb_days, next_month "
                    "FROM account_payment_term_line "
                    "WHERE payment_term_id=:tid ORDER BY sequence"
                ),
                {"tid": payment_term_id},
            )
            term_lines = [dict(row._mapping) for row in rows]

        percent_lines = [tl for tl in term_lines if tl["value"] == "percent"]
        if percent_lines:
            percent_total = sum(
                (Decimal(str(tl["value_amount"] or "0")) for tl in percent_lines), Decimal("0")
            )
            if abs(percent_total - Decimal("100")) > Decimal("0.001"):
                raise DodooError(
                    f"Payment term {payment_term_id}'s percent-type lines sum to "
                    f"{percent_total}, not 100% — cannot compute installments"
                )

        async with env.dml_conn() as conn:
            term_row = await conn.execute(
                text(
                    "SELECT early_discount, discount_percentage, discount_days "
                    "FROM account_payment_term WHERE id=:tid"
                ),
                {"tid": payment_term_id},
            )
            term = term_row.fetchone()

        early_discount = bool(term and term[0])
        discount_percentage = Decimal(str(term[1] if term else 0) or "0")
        discount_days = int(term[2] if term else 0) or 0

        def _with_discount(installment: dict) -> dict:
            if not early_discount:
                return installment
            installment["discount_date"] = invoice_date + datetime.timedelta(
                days=discount_days
            )
            installment["discount_amount"] = (
                installment["amount"] * (Decimal("100") - discount_percentage) / Decimal("100")
            ).quantize(Decimal("0.01"))
            return installment

        if not term_lines:
            return [_with_discount({"due_date": invoice_date, "amount": amount_total})]

        installments = []
        remaining = amount_total
        for i, tl in enumerate(term_lines):
            due_date = _compute_due_date(
                invoice_date,
                tl["delay_type"] or "days_after",
                int(tl["nb_days"] or 0),
                bool(tl.get("next_month")),
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
            installments.append(_with_discount({"due_date": due_date, "amount": inst_amount}))
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
    next_month = Boolean(default=False)

    @classmethod
    async def _check_percent_sum(
        cls,
        env: Environment,
        payment_term_id: int,
        exclude_id: int | None,
        incoming_value: str | None,
        incoming_amount: Any,
    ) -> None:
        """FR-017: percent-type lines on a term must never exceed 100% (checked on
        every write, so an obviously-invalid state is rejected immediately), and
        must sum to *exactly* 100% before the term can actually be used
        (enforced defensively in :meth:`compute_installments` too, since lines
        are added one at a time — a term is legitimately "incomplete" between
        its first and last line write).

        Only validates when the line being written (created or updated) is
        itself percent-type — a term is free to mix in fixed-type lines, which
        don't participate in this sum.
        """
        if incoming_value != "percent":
            return
        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT value_amount FROM account_payment_term_line "
                    "WHERE payment_term_id = :tid AND value = 'percent' AND id <> :excl"
                ),
                {"tid": payment_term_id, "excl": exclude_id or 0},
            )
            total = sum((Decimal(str(r[0] or "0")) for r in rows), Decimal("0"))
        total += Decimal(str(incoming_amount or "0"))
        if total > Decimal("100.001"):
            raise DodooError(
                f"Payment term {payment_term_id}'s percent-type lines would exceed 100% "
                f"(currently {total})"
            )

    @classmethod
    async def _percent_total(cls, env: Environment, payment_term_id: int) -> Decimal:
        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT value_amount FROM account_payment_term_line "
                    "WHERE payment_term_id = :tid AND value = 'percent'"
                ),
                {"tid": payment_term_id},
            )
            return sum((Decimal(str(r[0] or "0")) for r in rows), Decimal("0"))

    @classmethod
    async def create(cls, env: Environment, vals: dict[str, Any]) -> int:
        if vals.get("payment_term_id"):
            await cls._check_percent_sum(
                env, vals["payment_term_id"], None, vals.get("value"), vals.get("value_amount")
            )
        return await super().create(env, vals)

    @classmethod
    async def write(cls, env: Environment, ids: list[int], vals: dict[str, Any]) -> bool:
        if "value" in vals or "value_amount" in vals:
            for line_id in ids:
                records = await super().read(
                    env, [line_id], ["payment_term_id", "value", "value_amount"]
                )
                if not records:
                    continue
                rec = records[0]
                merged_value = vals.get("value", rec["value"])
                merged_amount = vals.get("value_amount", rec["value_amount"])
                await cls._check_percent_sum(
                    env, rec["payment_term_id"], line_id, merged_value, merged_amount
                )
        return await super().write(env, ids, vals)
