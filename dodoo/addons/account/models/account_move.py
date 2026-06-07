from __future__ import annotations

import datetime
import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Boolean, Char, Date, Many2one, Monetary, Selection, Text
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

    # ---- Tax computation ----

    @classmethod
    async def _compute_tax_lines(cls, conn, move_id: int, move_type: str) -> None:
        """Round-globally tax computation (ADR-003).

        1. Fetch product lines + their tax_ids.
        2. Validate tax type_tax_use vs move_type.
        3. Accumulate raw amounts by tax_id (round_globally).
        4. Delete existing auto-generated lines.
        5. Insert new tax lines.
        """
        # Manual entries — no auto tax/payment_term generation
        if move_type == "entry":
            return

        # Fetch product lines
        prod_rows = await conn.execute(
            text(
                "SELECT ml.id, ml.debit, ml.credit, ml.account_id, ml.date, ml.currency_id "
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

        # Collect all tax_ids for each product line
        # raw_tax_amounts: tax_id → accumulated raw Decimal
        raw_tax_amounts: dict[int, Decimal] = {}
        tax_meta: dict[int, dict] = (
            {}
        )  # tax_id → {amount_type, amount, account_id, type_tax_use}

        for pl in product_lines:
            line_id = pl["id"]
            tax_rows = await conn.execute(
                text(
                    "SELECT t.id, t.type_tax_use, t.amount_type, t.amount, t.price_include, "
                    "       r.account_id AS rep_account_id "
                    "FROM account_move_line_tax_rel rel "
                    "JOIN account_tax t ON t.id = rel.tax_id "
                    "LEFT JOIN account_tax_repartition_line r ON r.tax_id = t.id "
                    "   AND r.document_type = 'invoice' AND r.repartition_type = 'tax' "
                    "WHERE rel.move_line_id = :lid"
                ),
                {"lid": line_id},
            )
            taxes = [dict(row._mapping) for row in tax_rows]

            base = Decimal(str(pl["debit"])) - Decimal(str(pl["credit"]))

            for tax in taxes:
                tid = tax["id"]
                tuse = tax["type_tax_use"]

                # Validate type_tax_use compatibility (T018 requirement)
                if move_type in _SALE_TYPES and tuse == "purchase":
                    raise DodooError(
                        f"Purchase tax (id={tid}) cannot be applied to a sale move (move_type={move_type})"
                    )
                if move_type in _PURCHASE_TYPES and tuse == "sale":
                    raise DodooError(
                        f"Sale tax (id={tid}) cannot be applied to a purchase move (move_type={move_type})"
                    )

                from dodoo.addons.account.models.account_tax import AccountTax

                raw = AccountTax._compute_amount(tax, base)
                raw_tax_amounts[tid] = raw_tax_amounts.get(tid, Decimal("0")) + raw
                if tid not in tax_meta:
                    tax_meta[tid] = tax

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

        # Round globally: one rounding per tax
        rounded: dict[int, Decimal] = {
            tid: _round(raw, rounding) for tid, raw in raw_tax_amounts.items()
        }

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
                ],
            )
            if not records:
                raise DodooError(f"account.move {move_id} not found")
            rec = records[0]
            if rec["state"] != "draft":
                raise DodooError(f"Move {move_id} is not in draft state")

            move_type = rec.get("move_type", "entry")

            async with env.dml_conn() as conn:
                # Run round-globally tax computation
                await cls._compute_tax_lines(conn, move_id, move_type)
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
    ) -> list[int]:
        """Create and post reversal moves; auto-reconcile AR/AP lines."""

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

            await cls.action_post(env, [rev_id])
            reversal_ids.append(rev_id)

            _log.info(
                "account.move reversed",
                extra={
                    "model": "account.move",
                    "record_id": move_id,
                    "reversal_id": rev_id,
                    "event": "action_reverse",
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
