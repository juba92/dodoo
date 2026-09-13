from __future__ import annotations

import datetime
import logging
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import (
    Boolean,
    Char,
    Date,
    Integer,
    Many2one,
    Monetary,
    Selection,
    Text,
)
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)

MOVE_TYPE_CHOICES = [
    ("entry", "Journal Entry"),
    ("out_invoice", "Customer Invoice"),
    ("out_refund", "Customer Credit Note"),
    ("in_invoice", "Vendor Bill"),
    ("in_refund", "Vendor Credit Note"),
    ("out_receipt", "Customer Receipt"),
    ("in_receipt", "Vendor Receipt"),
]

STATE_CHOICES = [
    ("draft", "Draft"),
    ("posted", "Posted"),
    ("cancel", "Cancelled"),
]

PAYMENT_STATE_CHOICES = [
    ("not_paid", "Not Paid"),
    ("in_payment", "In Payment"),
    ("paid", "Paid"),
    ("partial", "Partially Paid"),
    ("reversed", "Reversed"),
    ("blocked", "Blocked"),
]

_INVOICE_TYPES = frozenset(
    {
        "out_invoice",
        "out_refund",
        "in_invoice",
        "in_refund",
        "out_receipt",
        "in_receipt",
    }
)

_SALE_TYPES = frozenset({"out_invoice", "out_refund", "out_receipt"})
_PURCHASE_TYPES = frozenset({"in_invoice", "in_refund", "in_receipt"})

_JOURNAL_PREFIX: dict[str, str] = {
    "out_invoice": "INV",
    "out_refund": "RINV",
    "in_invoice": "BILL",
    "in_refund": "RBILL",
    "out_receipt": "PAY",
    "in_receipt": "PAY",
    "entry": "MISC",
}

_REVERSE_TYPE: dict[str, str] = {
    "out_invoice": "out_refund",
    "out_refund": "out_invoice",
    "in_invoice": "in_refund",
    "in_refund": "in_invoice",
    "entry": "entry",
    "out_receipt": "out_refund",
    "in_receipt": "in_refund",
}

_BALANCE_SQL = """
SELECT
    ROUND(SUM(debit)::NUMERIC, 2),
    ROUND(SUM(credit)::NUMERIC, 2)
FROM account_move_line
WHERE move_id = :move_id
  AND display_type NOT IN ('line_section', 'line_note')
"""

_LINE_COUNT_SQL = """
SELECT COUNT(*) FROM account_move_line
WHERE move_id = :move_id
  AND display_type NOT IN ('line_section', 'line_note')
"""

_AMOUNTS_SQL = """
SELECT
    ROUND(ABS(SUM(CASE WHEN display_type = 'product' THEN debit - credit ELSE 0 END))::NUMERIC, 2) AS untaxed,
    ROUND(ABS(SUM(CASE WHEN display_type = 'tax' THEN debit - credit ELSE 0 END))::NUMERIC, 2) AS tax_total,
    ROUND(ABS(SUM(CASE WHEN display_type = 'payment_term' THEN debit - credit ELSE 0 END))::NUMERIC, 2) AS total
FROM account_move_line
WHERE move_id = :move_id
"""


def _round(amount: Decimal, rounding: int = 2) -> Decimal:
    return amount.quantize(Decimal(10) ** -rounding, rounding=ROUND_HALF_UP)


class AccountMove(BaseModel):
    _name = "account.move"

    name = Char(size=64)
    move_type = Selection(MOVE_TYPE_CHOICES, default="entry")
    state = Selection(STATE_CHOICES, default="draft")
    payment_state = Selection(PAYMENT_STATE_CHOICES, default="not_paid")
    journal_id = Many2one("account.journal", required=True)
    company_id = Many2one("res.company", required=True)
    currency_id = Many2one("res.currency", required=True)
    partner_id = Many2one("res.partner")
    date = Date(required=True)
    invoice_date = Date()
    invoice_date_due = Date()
    invoice_payment_term_id = Many2one("account.payment.term")
    ref = Char(size=256)
    narration = Text()
    amount_untaxed = Monetary()
    amount_tax = Monetary()
    amount_total = Monetary()
    amount_residual = Monetary()
    reversed_entry_id = Many2one("account.move")
    posted_before = Boolean(default=False)
    debit_origin_id = Many2one("account.move")
    down_payment_origin_id = Many2one("account.move")
    invoice_cash_rounding_id = Many2one("account.cash.rounding")
    inalterable_hash = Char(size=64)
    secure_sequence_number = Integer()

    # ---- Multi-currency ----

    @classmethod
    async def _apply_fx_conversion(
        cls,
        conn,
        move_id: int,
        move_currency_id: int,
        company_id: int,
        move_date,
    ) -> None:
        """FR-024: for a move whose currency differs from the company's, convert
        each line's ``amount_currency`` into company-currency ``debit``/``credit``
        using the rate applicable to the move's date — ``currency_id`` stops being
        decorative. A line with no ``amount_currency`` set is left untouched
        (manual entries in company currency don't set it at all).
        """
        company_row = await conn.execute(
            text("SELECT currency_id FROM res_company WHERE id = :cid"),
            {"cid": company_id},
        )
        crow = company_row.fetchone()
        company_currency_id = crow[0] if crow else None
        if not company_currency_id or move_currency_id == company_currency_id:
            return

        if isinstance(move_date, str):
            move_date = datetime.date.fromisoformat(move_date)
        rate_row = await conn.execute(
            text(
                "SELECT rate FROM res_currency_rate "
                "WHERE currency_id = :cid AND rate_date <= :dt "
                "ORDER BY rate_date DESC LIMIT 1"
            ),
            {"cid": move_currency_id, "dt": move_date or datetime.date.today()},
        )
        rrow = rate_row.fetchone()
        if not rrow:
            raise DodooError(
                f"No exchange rate found for currency {move_currency_id} on or before "
                f"{move_date} — enter one via res.currency.rate before posting"
            )
        rate = Decimal(str(rrow[0]))

        lines_row = await conn.execute(
            text(
                "SELECT id, amount_currency FROM account_move_line "
                "WHERE move_id = :mid AND amount_currency IS NOT NULL AND amount_currency <> 0"
            ),
            {"mid": move_id},
        )
        for line_id, amount_currency in [(r[0], r[1]) for r in lines_row]:
            ac = Decimal(str(amount_currency))
            converted = (ac * rate).copy_abs()
            debit = converted if ac > 0 else Decimal("0")
            credit = Decimal("0") if ac > 0 else converted
            await conn.execute(
                text(
                    "UPDATE account_move_line SET debit=:d, credit=:c, balance=:bal, "
                    "write_date=now() WHERE id=:lid"
                ),
                {"d": str(debit), "c": str(credit), "bal": str(debit - credit), "lid": line_id},
            )

    @classmethod
    async def revalue_currency_balances(
        cls, env: Environment, company_id: int, as_of: datetime.date, uid: int | None = None
    ) -> list[dict]:
        """FR-026: period-end unrealized currency gain/loss revaluation.

        For every open (``reconciled=False``) foreign-currency AR/AP line, posts
        one adjustment move dated ``as_of`` to the exchange accounts, and
        immediately creates its next-day reversal in draft (reversible next
        period without affecting realized results).
        """
        async with env.dml_conn() as conn:
            company_row = await conn.execute(
                text(
                    "SELECT currency_id, income_currency_exchange_account_id, "
                    "       expense_currency_exchange_account_id "
                    "FROM res_company WHERE id = :cid"
                ),
                {"cid": company_id},
            )
            company = company_row.fetchone()
            if not company:
                raise DodooError(f"Company {company_id} not found")
            company_currency_id, income_acct, expense_acct = company
            if not income_acct or not expense_acct:
                raise DodooError(
                    "Company has no income/expense currency exchange account configured"
                )

            open_rows = await conn.execute(
                text(
                    "SELECT ml.id, ml.account_id, ml.currency_id, ml.amount_currency, "
                    "       ml.amount_residual "
                    "FROM account_move_line ml "
                    "JOIN account_account a ON a.id = ml.account_id "
                    "JOIN account_move m ON m.id = ml.move_id "
                    "WHERE m.company_id = :cid AND m.state = 'posted' "
                    "  AND ml.reconciled = FALSE AND ml.currency_id IS NOT NULL "
                    "  AND ml.currency_id <> :company_currency "
                    "  AND a.account_type IN ('asset_receivable', 'liability_payable') "
                    "  AND ABS(ml.amount_residual) > 0"
                ),
                {"cid": company_id, "company_currency": company_currency_id},
            )
            open_lines = [dict(r._mapping) for r in open_rows]

        entries = []
        for line in open_lines:
            async with env.dml_conn() as conn:
                rate_row = await conn.execute(
                    text(
                        "SELECT rate FROM res_currency_rate "
                        "WHERE currency_id = :cid AND rate_date <= :dt "
                        "ORDER BY rate_date DESC LIMIT 1"
                    ),
                    {"cid": line["currency_id"], "dt": as_of},
                )
                rrow = rate_row.fetchone()
            if not rrow:
                continue
            rate = Decimal(str(rrow[0]))
            revalued_company_amount = abs(Decimal(str(line["amount_currency"]))) * rate
            current_residual = Decimal(str(line["amount_residual"]))
            diff = revalued_company_amount - abs(current_residual)
            if abs(diff) < Decimal("0.01"):
                continue

            # A receivable (positive residual) revalued UP is a gain; a payable
            # (negative residual) revalued UP (owing more) is a loss — the two
            # account types invert the same `diff > 0` sign.
            is_receivable_side = current_residual >= 0
            is_gain = (diff > 0) == is_receivable_side
            gain_or_loss_account = income_acct if is_gain else expense_acct
            amount = abs(diff)

            # Plain balanced adjustment: move `amount` further onto the AR/AP
            # account's own side (receivable → more debit; payable → more
            # credit), offset by the gain/loss account — no reconciliation,
            # the original open item is left exactly as open as it was.
            move_id = await cls._post_revaluation_entry(
                env,
                company_id=company_id,
                target_account_id=line["account_id"],
                offset_account_id=gain_or_loss_account,
                amount=amount,
                is_receivable_side=is_receivable_side,
                is_gain=is_gain,
                date=as_of,
                ref=f"Unrealized currency revaluation for line {line['id']}",
            )
            reversal_date = as_of + datetime.timedelta(days=1)
            reversal_ids = await cls.action_reverse(
                env, [move_id], date=reversal_date, auto_post=False
            )
            entries.append(
                {"move_id": move_id, "reversal_move_id": reversal_ids[0], "amount": str(amount)}
            )

        return entries

    @classmethod
    async def _post_revaluation_entry(
        cls,
        env: Environment,
        *,
        company_id: int,
        target_account_id: int,
        offset_account_id: int,
        amount: Decimal,
        is_receivable_side: bool,
        is_gain: bool,
        date: datetime.date,
        ref: str,
    ) -> int:
        """Post a balanced 2-line adjustment moving ``amount`` further onto
        ``target_account_id`` (the AR/AP account) against ``offset_account_id``
        (the gain/loss account) — no reconciliation; the original open item's
        own residual/reconciliation status is left untouched.
        """
        # Receivable + gain, or payable + loss -> debit the AR/AP account more.
        target_is_debit = is_receivable_side == is_gain
        d1, c1 = (amount, Decimal("0")) if target_is_debit else (Decimal("0"), amount)
        d2, c2 = (Decimal("0"), amount) if target_is_debit else (amount, Decimal("0"))

        async with env.dml_conn() as conn:
            jrow = await conn.execute(
                text(
                    "SELECT id FROM account_journal WHERE type='general' "
                    "AND company_id=:cid LIMIT 1"
                ),
                {"cid": company_id},
            )
            journal_id = jrow.scalar_one()

        move_id = await cls.create(
            env,
            {
                "move_type": "entry",
                "journal_id": journal_id,
                "company_id": company_id,
                "currency_id": (await cls._company_currency_id_for(env, company_id)),
                "date": date,
                "ref": ref,
                "state": "draft",
            },
        )
        async with env.dml_conn() as conn:
            await conn.execute(
                text(
                    "INSERT INTO account_move_line "
                    "(move_id, account_id, date, display_type, debit, credit, balance, "
                    "create_date, write_date) "
                    "VALUES (:mid, :acct, :dt, 'product', :d, :c, :bal, now(), now())"
                ),
                {
                    "mid": move_id,
                    "acct": target_account_id,
                    "dt": date,
                    "d": str(d1),
                    "c": str(c1),
                    "bal": str(d1 - c1),
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO account_move_line "
                    "(move_id, account_id, date, display_type, debit, credit, balance, "
                    "create_date, write_date) "
                    "VALUES (:mid, :acct, :dt, 'product', :d, :c, :bal, now(), now())"
                ),
                {
                    "mid": move_id,
                    "acct": offset_account_id,
                    "dt": date,
                    "d": str(d2),
                    "c": str(c2),
                    "bal": str(d2 - c2),
                },
            )
            await conn.commit()

        await cls.action_post(env, [move_id])
        return move_id

    @classmethod
    async def _company_currency_id_for(cls, env: Environment, company_id: int) -> int | None:
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text("SELECT currency_id FROM res_company WHERE id=:cid"), {"cid": company_id}
            )
            r = row.fetchone()
            return r[0] if r else None

    # ---- Tax computation ----

    @classmethod
    async def _compute_tax_lines(cls, conn, move_id: int, move_type: str) -> None:
        """Discount-net, price-include-aware, rounding-method-aware tax computation
        (FR-013/014/015, ADR-040).

        1. Fetch product lines (using ``price_subtotal`` — already net of any
           per-line ``discount``, FR-010/013 — as the tax base, not the raw
           ``debit - credit`` ledger value).
        2. Validate tax type_tax_use vs move_type.
        3. For each line, extract price-included taxes from the gross first
           (FR-014), then add on-top taxes on the resulting net base; rewrite the
           line's own ``price_subtotal``/``debit``/``credit`` to the true net
           amount so the ledger and the tax base never disagree.
        4. Accumulate raw amounts by tax_id, rounding either globally (default)
           or per-line, per ``res_company.tax_rounding_method`` (FR-015).
        5. Delete existing auto-generated lines; insert new tax lines.
        """
        # Manual entries — no auto tax/payment_term generation
        if move_type == "entry":
            return

        # Fetch product lines
        prod_rows = await conn.execute(
            text(
                "SELECT ml.id, ml.debit, ml.credit, ml.account_id, ml.date, ml.currency_id, "
                "       ml.price_subtotal "
                "FROM account_move_line ml "
                "WHERE ml.move_id = :mid AND ml.display_type = 'product'"
            ),
            {"mid": move_id},
        )
        product_lines = [dict(row._mapping) for row in prod_rows]

        if not product_lines:
            # No product lines — delete only leftover auto lines (not manual payment_term lines)
            await conn.execute(
                text(
                    "DELETE FROM account_move_line WHERE move_id=:mid "
                    "AND display_type IN ('tax','payment_term')"
                ),
                {"mid": move_id},
            )
            return

        # Company's tax rounding method (FR-015) — defaults to round_globally when unset.
        method_row = await conn.execute(
            text(
                "SELECT co.tax_rounding_method FROM account_move m "
                "JOIN res_company co ON co.id = m.company_id WHERE m.id = :mid"
            ),
            {"mid": move_id},
        )
        mrow = method_row.fetchone()
        round_per_line = bool(mrow and mrow[0] == "round_per_line")

        # Fetch currency rounding for this move
        rounding_row = await conn.execute(
            text(
                "SELECT c.rounding FROM account_move m "
                "JOIN res_currency c ON c.id = m.currency_id "
                "WHERE m.id = :mid"
            ),
            {"mid": move_id},
        )
        rr = rounding_row.fetchone()
        rounding = int(rr[0]) if rr else 2

        from dodoo.addons.account.models.account_tax import AccountTax

        # raw_tax_amounts: tax_id → accumulated raw (or per-line-rounded) signed Decimal
        raw_tax_amounts: dict[int, Decimal] = {}
        tax_meta: dict[int, dict] = {}

        for pl in product_lines:
            line_id = pl["id"]
            tax_rows = await conn.execute(
                text(
                    "SELECT t.id, t.type_tax_use, t.amount_type, t.amount, t.price_include, "
                    "       r.account_id AS rep_account_id, t.sequence "
                    "FROM account_move_line_tax_rel rel "
                    "JOIN account_tax t ON t.id = rel.tax_id "
                    "LEFT JOIN account_tax_repartition_line r ON r.tax_id = t.id "
                    "   AND r.document_type = 'invoice' AND r.repartition_type = 'tax' "
                    "WHERE rel.move_line_id = :lid "
                    "ORDER BY t.sequence, t.id"
                ),
                {"lid": line_id},
            )
            taxes = [dict(row._mapping) for row in tax_rows]

            for tax in taxes:
                tuse = tax["type_tax_use"]
                # Validate type_tax_use compatibility
                if move_type in _SALE_TYPES and tuse == "purchase":
                    raise DodooError(
                        f"Purchase tax (id={tax['id']}) cannot be applied to a sale move "
                        f"(move_type={move_type})"
                    )
                if move_type in _PURCHASE_TYPES and tuse == "sale":
                    raise DodooError(
                        f"Sale tax (id={tax['id']}) cannot be applied to a purchase move "
                        f"(move_type={move_type})"
                    )
                if tax["id"] not in tax_meta:
                    tax_meta[tax["id"]] = tax

            # Sign convention: whichever side (debit/purchase or credit/sale) is
            # already nonzero on this line determines the tax line's own side.
            sign = Decimal("1") if Decimal(str(pl["debit"])) >= Decimal(str(pl["credit"])) else Decimal("-1")

            # price_subtotal is the discount-net magnitude (FR-010/013); for a
            # price-included tax it is still gross-of-that-tax at this point.
            subtotal = pl.get("price_subtotal")
            gross_magnitude = (
                Decimal(str(subtotal))
                if subtotal not in (None, "")
                else abs(Decimal(str(pl["debit"])) - Decimal(str(pl["credit"])))
            )

            # 1) Extract price-included taxes from the gross first (FR-014),
            #    sequentially, so a line with more than one price-included tax
            #    still nets down correctly.
            net_magnitude = gross_magnitude
            for tax in taxes:
                if not tax["price_include"]:
                    continue
                if tax["amount_type"] == "percent":
                    rate = Decimal(str(tax["amount"] or 0))
                    extracted = net_magnitude - net_magnitude / (Decimal("1") + rate / Decimal("100"))
                else:
                    # division/fixed/group price-included taxes are computed on
                    # the running net base like their on-top counterparts —
                    # extraction only has a well-defined closed form for percent.
                    extracted = AccountTax._compute_amount(tax, net_magnitude)
                contribution = sign * extracted
                if round_per_line:
                    contribution = _round(contribution, rounding)
                raw_tax_amounts[tax["id"]] = raw_tax_amounts.get(tax["id"], Decimal("0")) + contribution
                net_magnitude -= extracted

            # 2) Add on-top (not price-included) taxes on the resulting net base.
            for tax in taxes:
                if tax["price_include"]:
                    continue
                amt = AccountTax._compute_amount(tax, net_magnitude)
                contribution = sign * amt
                if round_per_line:
                    contribution = _round(contribution, rounding)
                raw_tax_amounts[tax["id"]] = raw_tax_amounts.get(tax["id"], Decimal("0")) + contribution

            # Rewrite the line's own subtotal/ledger amount to the true net
            # value once any price-included tax has been extracted, so the
            # stored ledger and the tax base this method just used never
            # disagree (defense in depth against a caller sending a stale
            # debit/credit alongside price_unit/discount).
            net_magnitude = _round(net_magnitude, rounding)
            if net_magnitude != gross_magnitude:
                new_debit = net_magnitude if sign > 0 else Decimal("0")
                new_credit = Decimal("0") if sign > 0 else net_magnitude
                await conn.execute(
                    text(
                        "UPDATE account_move_line SET "
                        "price_subtotal=:ps, debit=:d, credit=:c, balance=:bal, "
                        "write_date=now() WHERE id=:lid"
                    ),
                    {
                        "ps": str(net_magnitude),
                        "d": str(new_debit),
                        "c": str(new_credit),
                        "bal": str(new_debit - new_credit),
                        "lid": line_id,
                    },
                )
            elif subtotal in (None, ""):
                # No price-included extraction happened but price_subtotal was
                # never stored (manual/API line) — persist it now so downstream
                # readers (reports, recompute_totals) see a consistent value.
                await conn.execute(
                    text(
                        "UPDATE account_move_line SET price_subtotal=:ps, write_date=now() "
                        "WHERE id=:lid"
                    ),
                    {"ps": str(net_magnitude), "lid": line_id},
                )

        # FR-015: when round_per_line, each line's contribution was already
        # rounded before being summed above — summing already-rounded amounts
        # here would double-round, so only round_globally rounds at this step.
        if round_per_line:
            rounded: dict[int, Decimal] = dict(raw_tax_amounts)
        else:
            rounded = {tid: _round(raw, rounding) for tid, raw in raw_tax_amounts.items()}

        # Delete existing auto lines
        await conn.execute(
            text(
                "DELETE FROM account_move_line WHERE move_id=:mid "
                "AND display_type IN ('tax', 'payment_term')"
            ),
            {"mid": move_id},
        )

        # Get accounting date from first product line
        acct_date = product_lines[0]["date"]
        if isinstance(acct_date, str):
            acct_date = datetime.date.fromisoformat(acct_date)

        # Insert tax lines
        for tid, amount in rounded.items():
            meta = tax_meta[tid]
            rep_account_id = meta.get("rep_account_id")
            if not rep_account_id:
                continue  # no repartition line account — skip

            # Tax line mirrors product line direction:
            # out_invoice (Cr revenue) → Cr tax; in_invoice (Dr expense) → Dr tax
            if amount >= 0:
                debit, credit = amount, Decimal("0")
            else:
                debit, credit = Decimal("0"), -amount

            await conn.execute(
                text(
                    "INSERT INTO account_move_line "
                    "(move_id, sequence, account_id, date, display_type, "
                    "debit, credit, balance, tax_line_id, create_date, write_date) "
                    "VALUES (:mid, 9999, :acct, :dt, 'tax', "
                    ":debit, :credit, :balance, :tax_id, now(), now())"
                ),
                {
                    "mid": move_id,
                    "acct": rep_account_id,
                    "dt": acct_date,
                    "debit": str(debit),
                    "credit": str(credit),
                    "balance": str(debit - credit),
                    "tax_id": tid,
                },
            )

    @classmethod
    async def _apply_cash_rounding(cls, conn, move_id: int, cash_rounding_id: int) -> None:
        """FR-030: round the invoice total to the profile's increment, adding a
        rounding line (``add_invoice_line``) or adjusting the largest tax line
        (``biggest_tax``) for the difference."""
        profile_row = await conn.execute(
            text(
                "SELECT rounding, rounding_method, strategy, account_id "
                "FROM account_cash_rounding WHERE id = :id"
            ),
            {"id": cash_rounding_id},
        )
        profile = profile_row.fetchone()
        if not profile:
            return
        increment, method, strategy, rounding_account_id = profile
        increment = Decimal(str(increment))
        if increment <= 0:
            return

        totals_row = await conn.execute(
            text(
                "SELECT COALESCE(SUM(debit - credit), 0) FROM account_move_line "
                "WHERE move_id = :mid AND display_type IN ('product', 'tax')"
            ),
            {"mid": move_id},
        )
        total = Decimal(str(totals_row.scalar_one() or "0"))
        sign = Decimal("1") if total >= 0 else Decimal("-1")
        magnitude = abs(total)

        steps = magnitude / increment
        if method == "up":
            steps = steps.to_integral_value(rounding=ROUND_CEILING)
        elif method == "down":
            steps = steps.to_integral_value(rounding=ROUND_FLOOR)
        else:
            steps = steps.to_integral_value(rounding=ROUND_HALF_UP)
        rounded_magnitude = steps * increment
        diff = sign * (rounded_magnitude - magnitude)  # signed adjustment to apply
        if abs(diff) < Decimal("0.0001"):
            return

        acct_date_row = await conn.execute(
            text(
                "SELECT date FROM account_move_line WHERE move_id=:mid "
                "AND display_type='product' LIMIT 1"
            ),
            {"mid": move_id},
        )
        acct_date = acct_date_row.scalar_one_or_none() or datetime.date.today()

        if strategy == "biggest_tax" and rounding_account_id is None:
            biggest_row = await conn.execute(
                text(
                    "SELECT id, debit, credit FROM account_move_line "
                    "WHERE move_id = :mid AND display_type = 'tax' "
                    "ORDER BY ABS(debit - credit) DESC LIMIT 1"
                ),
                {"mid": move_id},
            )
            biggest = biggest_row.fetchone()
            if biggest:
                line_id, debit, credit = biggest
                new_balance = (Decimal(str(debit)) - Decimal(str(credit))) + diff
                new_debit = new_balance if new_balance >= 0 else Decimal("0")
                new_credit = Decimal("0") if new_balance >= 0 else -new_balance
                await conn.execute(
                    text(
                        "UPDATE account_move_line SET debit=:d, credit=:c, balance=:bal, "
                        "write_date=now() WHERE id=:lid"
                    ),
                    {
                        "d": str(new_debit),
                        "c": str(new_credit),
                        "bal": str(new_balance),
                        "lid": line_id,
                    },
                )
                return
            # No tax line to adjust — fall through to add-invoice-line below.

        rounding_account = rounding_account_id
        if rounding_account is None:
            return  # add_invoice_line strategy with no configured account — nothing to do
        debit = diff if diff >= 0 else Decimal("0")
        credit = Decimal("0") if diff >= 0 else -diff
        await conn.execute(
            text(
                "INSERT INTO account_move_line "
                "(move_id, sequence, account_id, date, display_type, "
                "debit, credit, balance, create_date, write_date) "
                "VALUES (:mid, 9990, :acct, :dt, 'product', :d, :c, :bal, now(), now())"
            ),
            {
                "mid": move_id,
                "acct": rounding_account,
                "dt": acct_date,
                "d": str(debit),
                "c": str(credit),
                "bal": str(debit - credit),
            },
        )

    @classmethod
    async def _compute_payment_term_lines(
        cls, conn, move_id: int, move_type: str, partner_id: int | None, company_id: int
    ) -> None:
        """Auto-generate the AR/AP (payment_term) line that balances invoice moves."""
        if move_type not in _INVOICE_TYPES:
            return

        # Sum balances of non-payment_term lines
        bal_row = await conn.execute(
            text(
                "SELECT COALESCE(SUM(debit),0), COALESCE(SUM(credit),0) "
                "FROM account_move_line "
                "WHERE move_id=:mid AND display_type NOT IN ('line_section','line_note','payment_term')"
            ),
            {"mid": move_id},
        )
        row = bal_row.fetchone()
        total_debit = Decimal(str(row[0] or "0"))
        total_credit = Decimal(str(row[1] or "0"))
        imbalance = total_credit - total_debit  # positive → need a debit line

        if imbalance == 0:
            return  # Already balanced without a payment_term line

        # Determine AR or AP account
        is_receivable = move_type in _SALE_TYPES
        acct_type = "asset_receivable" if is_receivable else "liability_payable"

        ar_ap_account_id = None
        if partner_id:
            col = (
                "property_account_receivable_id"
                if is_receivable
                else "property_account_payable_id"
            )
            prow = await conn.execute(
                text(f"SELECT {col} FROM res_partner WHERE id=:pid"),
                {"pid": partner_id},
            )
            pdata = prow.fetchone()
            ar_ap_account_id = pdata[0] if pdata else None

        if not ar_ap_account_id:
            arow = await conn.execute(
                text(
                    "SELECT id FROM account_account "
                    "WHERE account_type=:atype AND company_id=:cid LIMIT 1"
                ),
                {"atype": acct_type, "cid": company_id},
            )
            arow_data = arow.fetchone()
            ar_ap_account_id = arow_data[0] if arow_data else None

        if not ar_ap_account_id:
            raise DodooError(f"No {acct_type} account found for company {company_id}")

        # Delete existing payment_term lines and re-insert
        await conn.execute(
            text(
                "DELETE FROM account_move_line WHERE move_id=:mid AND display_type='payment_term'"
            ),
            {"mid": move_id},
        )

        # imbalance > 0: credit > debit → need debit (AR/AP)
        if imbalance > 0:
            debit, credit = imbalance, Decimal("0")
        else:
            debit, credit = Decimal("0"), -imbalance

        # Get date from first product line
        dt_row = await conn.execute(
            text(
                "SELECT date FROM account_move_line WHERE move_id=:mid AND display_type='product' LIMIT 1"
            ),
            {"mid": move_id},
        )
        dt_data = dt_row.fetchone()
        acct_date = dt_data[0] if dt_data else datetime.date.today()
        if isinstance(acct_date, str):
            acct_date = datetime.date.fromisoformat(acct_date)

        bal = debit - credit
        # Insert with amount_residual = balance (the full unpaid amount initially)
        await conn.execute(
            text(
                "INSERT INTO account_move_line "
                "(move_id, sequence, account_id, partner_id, date, display_type, "
                "debit, credit, balance, amount_residual, create_date, write_date) "
                "VALUES (:mid, 9998, :acct, :pid, :dt, 'payment_term', "
                ":debit, :credit, :bal, :bal, now(), now())"
            ),
            {
                "mid": move_id,
                "acct": ar_ap_account_id,
                "pid": partner_id,
                "dt": acct_date,
                "debit": str(debit),
                "credit": str(credit),
                "bal": str(bal),
            },
        )

    # ---- Draft dynamic totals ----

    @classmethod
    async def recompute_totals(
        cls, env: Environment, ids: list[int]
    ) -> dict[int, dict[str, str]]:
        """Recompute ``amount_untaxed`` / ``amount_tax`` / ``amount_total`` for
        draft invoice moves from their product lines and each line's ``tax_ids``.

        This is the persisted counterpart of the live client-side preview: the
        SPA calls it after saving invoice lines so a re-opened draft shows the
        same figures. Posted moves are owned by :meth:`action_post` and are left
        untouched. Taxes are accumulated round-globally per tax (ADR-003).
        """
        from dodoo.addons.account.models.account_tax import AccountTax

        result: dict[int, dict[str, str]] = {}
        for move_id in ids:
            records = await super().read(
                env, [move_id], ["state", "move_type", "currency_id"]
            )
            if not records:
                raise DodooError(f"account.move {move_id} not found")
            rec = records[0]
            if rec["state"] == "posted":
                continue

            async with env.dml_conn() as conn:
                rounding_row = await conn.execute(
                    text("SELECT rounding FROM res_currency WHERE id = :cid"),
                    {"cid": rec["currency_id"]},
                )
                rr = rounding_row.fetchone()
                rounding = int(rr[0]) if rr else 2

                prod_rows = await conn.execute(
                    text(
                        "SELECT id, debit, credit, price_subtotal "
                        "FROM account_move_line "
                        "WHERE move_id = :mid AND display_type = 'product'"
                    ),
                    {"mid": move_id},
                )
                product_lines = [dict(r._mapping) for r in prod_rows]

                untaxed = Decimal("0")
                raw_tax_amounts: dict[int, Decimal] = {}
                for pl in product_lines:
                    subtotal = pl.get("price_subtotal")
                    base = (
                        Decimal(str(subtotal))
                        if subtotal not in (None, 0)
                        else abs(Decimal(str(pl["debit"])) - Decimal(str(pl["credit"])))
                    )
                    untaxed += base

                    line_total = base
                    tax_rows = await conn.execute(
                        text(
                            "SELECT t.id, t.amount_type, t.amount "
                            "FROM account_move_line_tax_rel rel "
                            "JOIN account_tax t ON t.id = rel.tax_id "
                            "WHERE rel.move_line_id = :lid"
                        ),
                        {"lid": pl["id"]},
                    )
                    for tax in (dict(r._mapping) for r in tax_rows):
                        amt = AccountTax._compute_amount(tax, base)
                        raw_tax_amounts[tax["id"]] = (
                            raw_tax_amounts.get(tax["id"], Decimal("0")) + amt
                        )
                        line_total += amt
                    await conn.execute(
                        text(
                            "UPDATE account_move_line "
                            "SET price_total = :pt, write_date = now() WHERE id = :lid"
                        ),
                        {"pt": str(_round(line_total, rounding)), "lid": pl["id"]},
                    )

                untaxed = _round(untaxed, rounding)
                tax_total = sum(
                    (_round(v, rounding) for v in raw_tax_amounts.values()),
                    Decimal("0"),
                )
                total = untaxed + tax_total

                await conn.execute(
                    text(
                        "UPDATE account_move SET "
                        "amount_untaxed = :u, amount_tax = :t, amount_total = :g, "
                        "write_date = now() WHERE id = :mid"
                    ),
                    {
                        "u": str(untaxed),
                        "t": str(tax_total),
                        "g": str(total),
                        "mid": move_id,
                    },
                )
                await conn.commit()

            result[move_id] = {
                "amount_untaxed": str(untaxed),
                "amount_tax": str(tax_total),
                "amount_total": str(total),
            }
        return result

    # ---- Posting ----

    @classmethod
    async def action_post(cls, env: Environment, ids: list[int]) -> bool:
        """Validate balance, assign sequence, transition to posted."""
        from dodoo.addons.account.models.account_sequence import get_next_sequence

        for move_id in ids:
            records = await super().read(
                env,
                [move_id],
                [
                    "state",
                    "move_type",
                    "date",
                    "journal_id",
                    "company_id",
                    "currency_id",
                    "partner_id",
                    "invoice_cash_rounding_id",
                ],
            )
            if not records:
                raise DodooError(f"account.move {move_id} not found")
            rec = records[0]
            if rec["state"] != "draft":
                raise DodooError(f"Move {move_id} is not in draft state")

            move_type = rec.get("move_type", "entry")

            async with env.dml_conn() as conn:
                # FR-024: convert amount_currency -> company-currency debit/credit
                # for a foreign-currency move, before tax/payment-term generation
                # (both of which read debit/credit as the base).
                await cls._apply_fx_conversion(
                    conn, move_id, rec["currency_id"], rec["company_id"], rec.get("date")
                )
                # Run round-globally tax computation
                await cls._compute_tax_lines(conn, move_id, move_type)
                # FR-030: apply cash rounding right after tax computation.
                if rec.get("invoice_cash_rounding_id"):
                    await cls._apply_cash_rounding(
                        conn, move_id, rec["invoice_cash_rounding_id"]
                    )
                # Auto-generate payment_term (AR/AP) line for invoice types
                await cls._compute_payment_term_lines(
                    conn, move_id, move_type, rec.get("partner_id"), rec["company_id"]
                )
                await conn.commit()

            async with env.dml_conn() as conn:
                # Must have at least one accounting line
                line_count = await conn.execute(
                    text(_LINE_COUNT_SQL), {"move_id": move_id}
                )
                if line_count.scalar_one() == 0:
                    raise DodooError(
                        f"Move {move_id}: cannot post an entry with no accounting lines"
                    )

                # Balance constraint (FR balance invariant)
                bal = await conn.execute(text(_BALANCE_SQL), {"move_id": move_id})
                row = bal.fetchone()
                total_debit = Decimal(str(row[0] or "0"))
                total_credit = Decimal(str(row[1] or "0"))
                if total_debit != total_credit:
                    raise DodooError(
                        f"Move {move_id} is not balanced: "
                        f"debit={total_debit} credit={total_credit} "
                        f"(imbalance={total_debit - total_credit})"
                    )

                # Assign sequence name
                prefix = _JOURNAL_PREFIX.get(move_type, "MISC")
                date_val = rec.get("date")
                if isinstance(date_val, str):
                    date_val = datetime.date.fromisoformat(date_val)
                year = date_val.year if date_val else datetime.date.today().year
                seq_no = await get_next_sequence(conn, prefix, year)
                name = f"{prefix}/{year}/{seq_no:04d}"

                # Compute header amounts
                amounts_row = await conn.execute(
                    text(_AMOUNTS_SQL), {"move_id": move_id}
                )
                amounts = amounts_row.fetchone()
                untaxed = Decimal(str(amounts[0] or "0"))
                tax_total = Decimal(str(amounts[1] or "0"))
                total = Decimal(str(amounts[2] or "0"))

                payment_state = (
                    "not_paid" if move_type in _INVOICE_TYPES else "not_paid"
                )

                await conn.execute(
                    text(
                        "UPDATE account_move SET "
                        "  state='posted', name=:name, posted_before=TRUE, "
                        "  amount_untaxed=:untaxed, amount_tax=:tax_total, "
                        "  amount_total=:total, amount_residual=:total, "
                        "  payment_state=:pstate, write_date=now() "
                        "WHERE id=:id"
                    ),
                    {
                        "name": name,
                        "id": move_id,
                        "untaxed": str(untaxed),
                        "tax_total": str(tax_total),
                        "total": str(total),
                        "pstate": payment_state,
                    },
                )
                await conn.commit()

            _log.info(
                "account.move posted",
                extra={
                    "model": "account.move",
                    "record_id": move_id,
                    "move_name": name,
                    "event": "action_post",
                    "move_type": move_type,
                },
            )

        return True

    @classmethod
    async def action_reset_to_draft(cls, env: Environment, ids: list[int]) -> bool:
        """Reset posted moves to draft; refuse if any payment_term line is reconciled."""
        for move_id in ids:
            records = await super().read(env, [move_id], ["state", "posted_before"])
            if not records:
                raise DodooError(f"account.move {move_id} not found")
            rec = records[0]
            if rec["state"] == "cancel":
                raise DodooError(f"Move {move_id} is cancelled; create a reversal")
            if rec["state"] == "draft":
                continue

            async with env.dml_conn() as conn:
                # Block reset if payment_term lines are reconciled
                row = await conn.execute(
                    text(
                        "SELECT COUNT(*) FROM account_partial_reconcile pr "
                        "JOIN account_move_line ml ON ml.id = pr.debit_move_id OR ml.id = pr.credit_move_id "
                        "WHERE ml.move_id = :mid"
                    ),
                    {"mid": move_id},
                )
                if row.scalar_one() > 0:
                    raise DodooError(
                        f"Move {move_id} has reconciled lines; unreconcile first"
                    )

                await conn.execute(
                    text(
                        "UPDATE account_move SET state='draft', write_date=now() WHERE id=:id"
                    ),
                    {"id": move_id},
                )
                await conn.commit()

            _log.info(
                "account.move reset to draft",
                extra={
                    "model": "account.move",
                    "record_id": move_id,
                    "event": "action_reset_to_draft",
                },
            )
        return True

    @classmethod
    async def action_reverse(
        cls,
        env: Environment,
        ids: list[int],
        date: datetime.date | None = None,
        journal_id: int | None = None,
        auto_post: bool = True,
    ) -> list[int]:
        """Create reversal moves (mirrored debit/credit); auto-reconcile AR/AP
        lines. FR-006: when ``auto_post`` is ``False``, the reversal is created
        and left in ``draft`` for the caller to review/adjust before posting."""

        reversal_ids = []
        for move_id in ids:
            records = await super().read(
                env,
                [move_id],
                [
                    "state",
                    "move_type",
                    "journal_id",
                    "company_id",
                    "currency_id",
                    "partner_id",
                ],
            )
            if not records:
                raise DodooError(f"account.move {move_id} not found")
            rec = records[0]
            if rec["state"] != "posted":
                raise DodooError(f"Move {move_id} must be posted to reverse")

            reversal_type = _REVERSE_TYPE.get(rec["move_type"], "entry")
            reversal_date = date or datetime.date.today()
            if isinstance(reversal_date, str):
                reversal_date = datetime.date.fromisoformat(reversal_date)

            # Fetch original lines (exclude section/note)
            async with env.dml_conn() as conn:
                orig_lines = await conn.execute(
                    text(
                        "SELECT account_id, partner_id, name, date, display_type, "
                        "       debit, credit, balance, currency_id, amount_currency "
                        "FROM account_move_line "
                        "WHERE move_id=:mid AND display_type NOT IN ('line_section','line_note')"
                    ),
                    {"mid": move_id},
                )
                lines = [dict(row._mapping) for row in orig_lines]

            # Create reversal move
            rev_id = await cls.create(
                env,
                {
                    "move_type": reversal_type,
                    "journal_id": journal_id or rec["journal_id"],
                    "company_id": rec["company_id"],
                    "currency_id": rec["currency_id"],
                    "partner_id": rec.get("partner_id"),
                    "date": reversal_date,
                    "invoice_date": reversal_date,
                    "reversed_entry_id": move_id,
                    "state": "draft",
                },
            )

            # Mirror lines with debit↔credit swapped
            async with env.dml_conn() as conn:
                for line in lines:
                    debit = Decimal(str(line["credit"]))
                    credit = Decimal(str(line["debit"]))
                    await conn.execute(
                        text(
                            "INSERT INTO account_move_line "
                            "(move_id, account_id, partner_id, name, date, display_type, "
                            "debit, credit, balance, currency_id, amount_currency, "
                            "create_date, write_date) "
                            "VALUES (:mid, :acct, :pid, :nm, :dt, :dtype, "
                            ":debit, :credit, :bal, :cid, :acur, now(), now())"
                        ),
                        {
                            "mid": rev_id,
                            "acct": line["account_id"],
                            "pid": line.get("partner_id"),
                            "nm": line.get("name"),
                            "dt": reversal_date,
                            "dtype": line["display_type"],
                            "debit": str(debit),
                            "credit": str(credit),
                            "bal": str(debit - credit),
                            "cid": line.get("currency_id"),
                            "acur": str(line.get("amount_currency") or "0"),
                        },
                    )
                await conn.commit()

            if auto_post:
                await cls.action_post(env, [rev_id])
            reversal_ids.append(rev_id)

            _log.info(
                "account.move reversed",
                extra={
                    "model": "account.move",
                    "record_id": move_id,
                    "reversal_id": rev_id,
                    "event": "action_reverse",
                    "auto_post": auto_post,
                },
            )

        return reversal_ids

    # ---- Payment state ----

    @classmethod
    async def _compute_payment_state(cls, env: Environment, move_id: int) -> str:
        """Compute payment_state from amount_residual on payment_term lines."""
        records = await super().read(
            env, [move_id], ["move_type", "amount_total", "reversed_entry_id"]
        )
        if not records:
            return "not_paid"
        rec = records[0]
        if rec["move_type"] not in _INVOICE_TYPES:
            return "not_paid"
        if rec.get("reversed_entry_id"):
            return "reversed"

        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT ROUND(SUM(amount_residual)::NUMERIC, 2) "
                    "FROM account_move_line "
                    "WHERE move_id=:mid AND display_type='payment_term'"
                ),
                {"mid": move_id},
            )
            residual = Decimal(str(row.scalar_one() or "0"))

        total = Decimal(str(rec.get("amount_total") or "0"))
        if residual == 0:
            return "paid"
        if residual >= total:
            return "not_paid"
        return "partial"

    # ---- Immutability guards ----

    @classmethod
    async def write(
        cls, env: Environment, ids: list[int], vals: dict[str, Any]
    ) -> bool:
        locked_fields = {
            "journal_id",
            "date",
            "move_type",
            "company_id",
            "currency_id",
            "partner_id",
            "invoice_payment_term_id",
        }
        for move_id in ids:
            records = await super().read(env, [move_id], ["state"])
            if records and records[0].get("state") == "posted":
                bad = locked_fields & set(vals.keys())
                if bad:
                    raise DodooError(
                        f"Move {move_id} is posted; cannot change: {', '.join(sorted(bad))}. "
                        "Reset to draft first."
                    )
        return await super().write(env, ids, vals)

    @classmethod
    async def unlink(cls, env: Environment, ids: list[int]) -> bool:
        for move_id in ids:
            records = await super().read(env, [move_id], ["state"])
            if records and records[0].get("state") == "posted":
                raise DodooError(
                    f"Move {move_id} is posted and cannot be deleted. Use action_reverse."
                )
        return await super().unlink(env, ids)
