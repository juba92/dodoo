from __future__ import annotations

import datetime
import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Many2one, Monetary
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)


class AccountFullReconcile(BaseModel):
    _name = "account.full.reconcile"

    company_id = Many2one("res.company", required=True)


class AccountPartialReconcile(BaseModel):
    _name = "account.partial.reconcile"

    debit_move_id = Many2one("account.move.line", required=True)
    credit_move_id = Many2one("account.move.line", required=True)
    amount = Monetary()
    debit_amount_currency = Monetary()
    credit_amount_currency = Monetary()
    full_reconcile_id = Many2one("account.full.reconcile")
    company_id = Many2one("res.company", required=True)

    @classmethod
    async def reconcile_lines(
        cls,
        env: Environment,
        debit_line_id: int,
        credit_line_id: int,
        amount: Decimal | None = None,
        writeoff_account_id: int | None = None,
        writeoff_journal_id: int | None = None,
    ) -> dict:
        """Partially or fully reconcile two move lines.

        debit_line_id  — line with positive balance (asset_receivable)
        credit_line_id — line with negative balance (or AP credit)
        amount         — amount to reconcile; defaults to min(residuals)
        writeoff_account_id/writeoff_journal_id — FR-020: when the two lines'
            residuals don't exactly cancel after reconciling ``amount``, post the
            leftover to this account (via an ordinary posted journal entry) and
            fully close both lines, instead of leaving a small residual behind.
        """
        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT ml.id, ml.move_id, ml.display_type, ml.account_id, "
                    "       ml.amount_residual, ml.reconciled, ml.currency_id, "
                    "       ml.amount_currency, m.company_id, m.date, "
                    "       a.reconcile AS acct_reconcile "
                    "FROM account_move_line ml "
                    "JOIN account_account a ON a.id = ml.account_id "
                    "JOIN account_move m ON m.id = ml.move_id "
                    "WHERE ml.id IN (:did, :cid) AND m.state = 'posted'"
                ),
                {"did": debit_line_id, "cid": credit_line_id},
            )
            line_map = {row[0]: dict(row._mapping) for row in rows}

        if debit_line_id not in line_map or credit_line_id not in line_map:
            raise DodooError("Both lines must exist and belong to posted moves")

        dl = line_map[debit_line_id]
        cl = line_map[credit_line_id]

        if not dl["acct_reconcile"] or not cl["acct_reconcile"]:
            raise DodooError("Both accounts must have reconcile=True")

        if dl["company_id"] != cl["company_id"]:
            raise DodooError("Cannot reconcile lines from different companies")

        d_residual = Decimal(str(dl["amount_residual"]))
        c_residual = Decimal(str(cl["amount_residual"]))

        # FR-022: when both lines share a foreign currency, compare/cap
        # full-reconciliation completion in transaction-currency terms instead
        # of (potentially FX-rate-drifted) company-currency amount_residual.
        # The remaining currency residual is the line's own amount_currency
        # less whatever this specific line has already contributed to prior
        # partial reconciliations.
        same_foreign_currency = bool(
            dl["currency_id"]
            and dl["currency_id"] == cl["currency_id"]
            and dl.get("amount_currency") not in (None, 0)
            and cl.get("amount_currency") not in (None, 0)
        )
        d_cur_residual = c_cur_residual = None
        max_amount = min(abs(d_residual), abs(c_residual))
        if same_foreign_currency:
            d_cur_residual = await cls._remaining_currency_residual(
                env, debit_line_id, Decimal(str(dl["amount_currency"])), as_debit=True
            )
            c_cur_residual = await cls._remaining_currency_residual(
                env, credit_line_id, Decimal(str(cl["amount_currency"])), as_debit=False
            )
            # Whichever side's currency residual is smaller may be tighter than
            # the company-currency residual once rates have drifted — cap by
            # both so full-reconciliation completion is currency-aware (FR-022).
            d_equiv = abs(d_residual) * abs(min(abs(d_cur_residual), abs(c_cur_residual))) / abs(
                d_cur_residual
            ) if d_cur_residual else max_amount
            max_amount = min(max_amount, d_equiv)

        if amount is None:
            amount = max_amount
        if amount > max_amount and not writeoff_account_id:
            raise DodooError(
                f"Reconcile amount {amount} exceeds min residual {max_amount}"
            )
        amount = min(amount, max_amount)

        company_id = dl["company_id"]

        # Proportional currency-amount share of this reconciliation, for the
        # account_partial_reconcile row and for the currency-residual check.
        d_cur_amt = c_cur_amt = None
        if same_foreign_currency and d_residual != 0 and c_residual != 0:
            d_cur_amt = (amount / abs(d_residual)) * d_cur_residual
            c_cur_amt = (amount / abs(c_residual)) * c_cur_residual

        async with env.dml_conn() as conn:
            result = await conn.execute(
                text(
                    "INSERT INTO account_partial_reconcile "
                    "(debit_move_id, credit_move_id, amount, debit_amount_currency, "
                    "credit_amount_currency, company_id, create_date, write_date) "
                    "VALUES (:did, :cid, :amt, :dca, :cca, :coid, now(), now()) RETURNING id"
                ),
                {
                    "did": debit_line_id,
                    "cid": credit_line_id,
                    "amt": str(amount),
                    "dca": str(d_cur_amt) if d_cur_amt is not None else "0",
                    "cca": str(c_cur_amt) if c_cur_amt is not None else "0",
                    "coid": company_id,
                },
            )
            partial_id = result.scalar_one()

            new_d_residual = d_residual - amount
            new_c_residual = c_residual + amount

            await conn.execute(
                text("UPDATE account_move_line SET amount_residual=:r WHERE id=:id"),
                {"r": str(new_d_residual), "id": debit_line_id},
            )
            await conn.execute(
                text("UPDATE account_move_line SET amount_residual=:r WHERE id=:id"),
                {"r": str(new_c_residual), "id": credit_line_id},
            )
            await conn.commit()

        writeoff_move_id = None
        # FR-020: a residual gap remains and a write-off account was supplied —
        # post the leftover and reconcile it against whichever line is still open.
        gap = None
        if abs(new_d_residual) >= Decimal("0.01") and writeoff_account_id:
            gap = new_d_residual
            open_line_id, open_account_id = debit_line_id, dl["account_id"]
        elif abs(new_c_residual) >= Decimal("0.01") and writeoff_account_id:
            gap = new_c_residual
            open_line_id, open_account_id = credit_line_id, cl["account_id"]

        if gap is not None and abs(gap) >= Decimal("0.01"):
            writeoff_move_id, writeoff_line_id = await cls._post_writeoff(
                env,
                company_id=company_id,
                journal_id=writeoff_journal_id,
                target_account_id=open_account_id,
                offset_account_id=writeoff_account_id,
                amount=gap,
                date=dl.get("date"),
                ref=f"Write-off for reconciliation {partial_id}",
            )
            if gap > 0:
                await cls.reconcile_lines(env, open_line_id, writeoff_line_id)
            else:
                await cls.reconcile_lines(env, writeoff_line_id, open_line_id)
            new_d_residual = Decimal("0") if open_line_id == debit_line_id else new_d_residual
            new_c_residual = Decimal("0") if open_line_id == credit_line_id else new_c_residual

        # FR-025: same transaction-currency exposure fully matched from at
        # least one side, but the company-currency residuals don't net to
        # zero because the two lines were booked at different rates — the gap
        # is a realized exchange gain/loss, not a real open balance. Once one
        # side's *entire* currency exposure is consumed, the two lines
        # represent the identical currency amount, so the other side's
        # leftover company-currency residual is FX drift by definition (it
        # was capped below its own full currency-equivalent amount by
        # `max_amount`'s min() over both sides' company-currency residuals) —
        # this is exactly why both sides don't reach zero currency residual
        # simultaneously when rates differ. Auto-post it to the company's
        # exchange accounts (skipped when an explicit write-off above already
        # closed the gap, or the currencies aren't foreign/matched, or no
        # exchange accounts are configured).
        fx_move_id = None
        if gap is None and same_foreign_currency and d_cur_amt is not None and c_cur_amt is not None:
            d_cur_left = d_cur_residual - d_cur_amt
            c_cur_left = c_cur_residual - c_cur_amt
            currency_fully_matched = (
                abs(d_cur_left) < Decimal("0.01") or abs(c_cur_left) < Decimal("0.01")
            )
            fx_gap = None
            if currency_fully_matched:
                if abs(new_d_residual) >= Decimal("0.01"):
                    fx_gap = new_d_residual
                    fx_open_line_id, fx_open_account_id = debit_line_id, dl["account_id"]
                elif abs(new_c_residual) >= Decimal("0.01"):
                    fx_gap = new_c_residual
                    fx_open_line_id, fx_open_account_id = credit_line_id, cl["account_id"]

            if fx_gap is not None and abs(fx_gap) >= Decimal("0.01"):
                income_account_id, expense_account_id = await cls._exchange_accounts(
                    env, company_id
                )
                # fx_gap > 0: the still-open (debit-side) line needed more
                # company currency than was received — a loss. fx_gap < 0:
                # more was received/paid than the receivable/payable required
                # — a gain.
                offset_account_id = expense_account_id if fx_gap > 0 else income_account_id
                if offset_account_id is not None:
                    fx_move_id, fx_line_id = await cls._post_writeoff(
                        env,
                        company_id=company_id,
                        journal_id=None,
                        target_account_id=fx_open_account_id,
                        offset_account_id=offset_account_id,
                        amount=fx_gap,
                        date=dl.get("date"),
                        ref=f"Realized exchange gain/loss for reconciliation {partial_id}",
                    )
                    if fx_gap > 0:
                        await cls.reconcile_lines(env, fx_open_line_id, fx_line_id)
                    else:
                        await cls.reconcile_lines(env, fx_line_id, fx_open_line_id)
                    new_d_residual = (
                        Decimal("0") if fx_open_line_id == debit_line_id else new_d_residual
                    )
                    new_c_residual = (
                        Decimal("0") if fx_open_line_id == credit_line_id else new_c_residual
                    )

        # Full reconcile if both residuals hit zero
        full_id = None
        if abs(new_d_residual) < Decimal("0.01") and abs(new_c_residual) < Decimal("0.01"):
            async with env.dml_conn() as conn:
                fr_result = await conn.execute(
                    text(
                        "INSERT INTO account_full_reconcile (company_id, create_date, write_date) "
                        "VALUES (:coid, now(), now()) RETURNING id"
                    ),
                    {"coid": company_id},
                )
                full_id = fr_result.scalar_one()
                await conn.execute(
                    text(
                        "UPDATE account_move_line SET reconciled=TRUE, full_reconcile_id=:fid "
                        "WHERE id IN (:did, :cid)"
                    ),
                    {"fid": full_id, "did": debit_line_id, "cid": credit_line_id},
                )
                await conn.execute(
                    text(
                        "UPDATE account_partial_reconcile SET full_reconcile_id=:fid WHERE id=:pid"
                    ),
                    {"fid": full_id, "pid": partial_id},
                )
                await conn.commit()

        _log.info(
            "account.partial.reconcile created",
            extra={
                "model": "account.partial.reconcile",
                "record_id": partial_id,
                "event": "reconcile_lines",
                "debit_line_id": debit_line_id,
                "credit_line_id": credit_line_id,
                "amount": str(amount),
                "full_reconcile_id": full_id,
                "writeoff_move_id": writeoff_move_id,
                "fx_move_id": fx_move_id,
            },
        )

        return {
            "partial_id": partial_id,
            "full_reconcile_id": full_id,
            "writeoff_move_id": writeoff_move_id,
            "fx_move_id": fx_move_id,
        }

    @classmethod
    async def _post_writeoff(
        cls,
        env: Environment,
        *,
        company_id: int,
        journal_id: int | None,
        target_account_id: int,
        offset_account_id: int,
        amount: Decimal,
        date,
        ref: str,
    ) -> tuple[int, int]:
        """Post a balanced 2-line entry closing ``amount`` of residual on
        ``target_account_id`` against ``offset_account_id`` (a write-off or an
        FX gain/loss account). Returns ``(move_id, target_line_id)`` — the id of
        the newly-created line on ``target_account_id`` for the caller to
        reconcile against the original open line.
        """
        from dodoo.addons.account.models.account_move import AccountMove

        if journal_id is None:
            async with env.dml_conn() as conn:
                jrow = await conn.execute(
                    text(
                        "SELECT id FROM account_journal WHERE type='general' "
                        "AND company_id=:cid LIMIT 1"
                    ),
                    {"cid": company_id},
                )
                journal_id = jrow.scalar_one()

        move_id = await AccountMove.create(
            env,
            {
                "move_type": "entry",
                "journal_id": journal_id,
                "company_id": company_id,
                "currency_id": (await cls._company_currency_id(env, company_id)),
                "date": date or datetime.date.today(),
                "ref": ref,
                "state": "draft",
            },
        )
        magnitude = abs(amount)
        # amount > 0 means the debit-side line was left open (still owes money) —
        # close it with a credit; amount < 0 closes an open credit-side line with
        # a debit. The offset line takes the opposite side.
        if amount > 0:
            d1, c1 = Decimal("0"), magnitude
            d2, c2 = magnitude, Decimal("0")
        else:
            d1, c1 = magnitude, Decimal("0")
            d2, c2 = Decimal("0"), magnitude

        async with env.dml_conn() as conn:
            target_row = await conn.execute(
                text(
                    "INSERT INTO account_move_line "
                    "(move_id, account_id, date, display_type, debit, credit, balance, "
                    "amount_residual, create_date, write_date) "
                    "VALUES (:mid, :acct, :dt, 'payment_term', :d, :c, :bal, :bal, now(), now()) "
                    "RETURNING id"
                ),
                {
                    "mid": move_id,
                    "acct": target_account_id,
                    "dt": date or datetime.date.today(),
                    "d": str(d1),
                    "c": str(c1),
                    "bal": str(d1 - c1),
                },
            )
            target_line_id = target_row.scalar_one()
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
                    "dt": date or datetime.date.today(),
                    "d": str(d2),
                    "c": str(c2),
                    "bal": str(d2 - c2),
                },
            )
            await conn.commit()

        await AccountMove.action_post(env, [move_id])
        return move_id, target_line_id

    @classmethod
    async def _exchange_accounts(
        cls, env: Environment, company_id: int
    ) -> tuple[int | None, int | None]:
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT income_currency_exchange_account_id, "
                    "expense_currency_exchange_account_id FROM res_company WHERE id=:cid"
                ),
                {"cid": company_id},
            )
            r = row.fetchone()
            return (r[0], r[1]) if r else (None, None)

    @classmethod
    async def _company_currency_id(cls, env: Environment, company_id: int) -> int | None:
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text("SELECT currency_id FROM res_company WHERE id=:cid"), {"cid": company_id}
            )
            r = row.fetchone()
            return r[0] if r else None

    @classmethod
    async def _remaining_currency_residual(
        cls, env: Environment, line_id: int, amount_currency: Decimal, as_debit: bool
    ) -> Decimal:
        """FR-022: a line's own ``amount_currency`` less whatever this line has
        already contributed (in currency terms) to prior partial reconciliations —
        there is no stored running "currency residual" field, so this is derived
        from the ``account_partial_reconcile`` history each time.
        """
        col = "debit_amount_currency" if as_debit else "credit_amount_currency"
        fk = "debit_move_id" if as_debit else "credit_move_id"
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    f"SELECT COALESCE(SUM({col}), 0) FROM account_partial_reconcile "
                    f"WHERE {fk} = :lid"
                ),
                {"lid": line_id},
            )
            already = Decimal(str(row.scalar_one() or "0"))
        return amount_currency - already

    @classmethod
    async def suggest_matches(
        cls, env: Environment, payment_id: int, limit: int = 10
    ) -> list[dict]:
        """FR-021: rank open, unreconciled payment_term lines for the payment's
        partner by amount closeness then reference/label trigram similarity —
        advisory only, never auto-reconciles.
        """
        async with env.dml_conn() as conn:
            prow = await conn.execute(
                text(
                    "SELECT p.partner_id, p.amount, p.ref FROM account_payment p WHERE p.id=:pid"
                ),
                {"pid": payment_id},
            )
            pay = prow.fetchone()
            if not pay:
                raise DodooError(f"account.payment {payment_id} not found")
            partner_id, amount, ref = pay

            rows = await conn.execute(
                text(
                    "SELECT ml.id AS move_line_id, m.name AS move_name, "
                    "       ml.amount_residual, "
                    "       ABS(ml.amount_residual - :amt) AS amount_gap, "
                    "       similarity(COALESCE(ml.name, ''), :ref) AS ref_similarity "
                    "FROM account_move_line ml "
                    "JOIN account_move m ON m.id = ml.move_id "
                    "WHERE ml.partner_id = :pid AND ml.display_type = 'payment_term' "
                    "  AND ml.reconciled = FALSE AND m.state = 'posted' "
                    "ORDER BY amount_gap ASC, ref_similarity DESC "
                    "LIMIT :lim"
                ),
                {"amt": float(amount or 0), "ref": ref or "", "pid": partner_id, "lim": limit},
            )
            candidates = [dict(r._mapping) for r in rows]

        return [
            {
                "move_line_id": c["move_line_id"],
                "move_name": c["move_name"],
                "amount_residual": str(c["amount_residual"]),
                "score": 1.0 / (1.0 + float(c["amount_gap"] or 0)) + float(c["ref_similarity"] or 0),
            }
            for c in candidates
        ]

    @classmethod
    async def unreconcile(cls, env: Environment, line_id: int) -> bool:
        """Undo all reconciliations involving a given move line."""
        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT id, full_reconcile_id FROM account_partial_reconcile "
                    "WHERE debit_move_id=:lid OR credit_move_id=:lid"
                ),
                {"lid": line_id},
            )
            partials = [dict(row._mapping) for row in rows]

            if not partials:
                return True

            full_ids = {
                p["full_reconcile_id"] for p in partials if p["full_reconcile_id"]
            }
            partial_ids = [p["id"] for p in partials]

            # Collect all affected line ids
            aff_rows = await conn.execute(
                text(
                    "SELECT DISTINCT debit_move_id, credit_move_id "
                    "FROM account_partial_reconcile WHERE id = ANY(:pids)"
                ),
                {"pids": partial_ids},
            )
            affected_ids = set()
            for row in aff_rows:
                affected_ids.add(row[0])
                affected_ids.add(row[1])

            # Delete partials
            await conn.execute(
                text("DELETE FROM account_partial_reconcile WHERE id = ANY(:pids)"),
                {"pids": partial_ids},
            )

            # Delete full reconcile if any
            if full_ids:
                await conn.execute(
                    text("DELETE FROM account_full_reconcile WHERE id = ANY(:fids)"),
                    {"fids": list(full_ids)},
                )

            # Reset affected lines
            await conn.execute(
                text(
                    "UPDATE account_move_line SET "
                    "reconciled=FALSE, full_reconcile_id=NULL, amount_residual=debit-credit "
                    "WHERE id = ANY(:lids)"
                ),
                {"lids": list(affected_ids)},
            )

            await conn.commit()

        _log.info(
            "account.partial.reconcile deleted (unreconcile)",
            extra={
                "model": "account.move.line",
                "record_id": line_id,
                "event": "unreconcile",
            },
        )
        return True
