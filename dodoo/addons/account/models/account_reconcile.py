from __future__ import annotations

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
    ) -> dict:
        """Partially or fully reconcile two move lines.

        debit_line_id  — line with positive balance (asset_receivable)
        credit_line_id — line with negative balance (or AP credit)
        amount         — amount to reconcile; defaults to min(residuals)
        """
        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT ml.id, ml.move_id, ml.display_type, ml.account_id, "
                    "       ml.amount_residual, ml.reconciled, m.company_id, "
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
        max_amount = min(abs(d_residual), abs(c_residual))

        if amount is None:
            amount = max_amount
        if amount > max_amount:
            raise DodooError(
                f"Reconcile amount {amount} exceeds min residual {max_amount}"
            )

        company_id = dl["company_id"]

        async with env.dml_conn() as conn:
            # Create partial reconcile record
            result = await conn.execute(
                text(
                    "INSERT INTO account_partial_reconcile "
                    "(debit_move_id, credit_move_id, amount, company_id, create_date, write_date) "
                    "VALUES (:did, :cid, :amt, :coid, now(), now()) RETURNING id"
                ),
                {
                    "did": debit_line_id,
                    "cid": credit_line_id,
                    "amt": str(amount),
                    "coid": company_id,
                },
            )
            partial_id = result.scalar_one()

            # Update residuals
            new_d_residual = d_residual - amount
            new_c_residual = (
                c_residual + amount
            )  # credit residual is negative → moves toward 0

            await conn.execute(
                text("UPDATE account_move_line SET amount_residual=:r WHERE id=:id"),
                {"r": str(new_d_residual), "id": debit_line_id},
            )
            await conn.execute(
                text("UPDATE account_move_line SET amount_residual=:r WHERE id=:id"),
                {"r": str(new_c_residual), "id": credit_line_id},
            )

            # Full reconcile if both residuals hit zero
            full_id = None
            if abs(new_d_residual) < Decimal("0.01") and abs(new_c_residual) < Decimal(
                "0.01"
            ):
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
            },
        )

        return {"partial_id": partial_id, "full_reconcile_id": full_id}

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
