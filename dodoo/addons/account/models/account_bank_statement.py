from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from dodoo.core.exceptions import DodooError
from dodoo.core.fields import Char, Date, Many2one, Monetary, Selection
from dodoo.core.models import BaseModel

if TYPE_CHECKING:
    from dodoo import Environment

_log = logging.getLogger(__name__)

STATEMENT_STATE_CHOICES = [
    ("open", "Open"),
    ("confirmed", "Confirmed"),
]


class AccountBankStatement(BaseModel):
    """A bank/cash journal's reported starting/ending balance for a period,
    with a set of dated transaction lines (FR-027, ADR-043)."""

    _name = "account.bank.statement"

    journal_id = Many2one("account.journal", required=True)
    date = Date(required=True)
    balance_start = Monetary()
    balance_end_real = Monetary()
    state = Selection(STATEMENT_STATE_CHOICES, default="open")
    company_id = Many2one("res.company", required=True)

    @classmethod
    async def get_status(cls, env: Environment, statement_id: int) -> dict[str, Any]:
        """FR-028: is this statement's own arithmetic complete —
        ``balance_start + SUM(lines.amount) == balance_end_real``?"""
        records = await super().read(
            env, [statement_id], ["balance_start", "balance_end_real"]
        )
        if not records:
            raise DodooError(f"account.bank.statement {statement_id} not found")
        rec = records[0]
        async with env.dml_conn() as conn:
            row = await conn.execute(
                text(
                    "SELECT COALESCE(SUM(amount), 0) FROM account_bank_statement_line "
                    "WHERE statement_id = :sid"
                ),
                {"sid": statement_id},
            )
            lines_total = Decimal(str(row.scalar_one() or "0"))
        computed = Decimal(str(rec["balance_start"] or "0")) + lines_total
        declared = Decimal(str(rec["balance_end_real"] or "0"))
        return {
            "complete": abs(computed - declared) < Decimal("0.01"),
            "computed_balance": str(computed),
            "declared_balance": str(declared),
        }

    @classmethod
    async def action_confirm(cls, env: Environment, statement_id: int) -> bool:
        """FR-028: confirming a statement checks continuity against the prior
        statement on the same journal (by date) — its ``balance_end_real`` must
        equal this one's ``balance_start``."""
        records = await super().read(
            env, [statement_id], ["journal_id", "date", "balance_start", "state"]
        )
        if not records:
            raise DodooError(f"account.bank.statement {statement_id} not found")
        rec = records[0]
        if rec["state"] == "confirmed":
            return True

        async with env.dml_conn() as conn:
            prior_row = await conn.execute(
                text(
                    "SELECT balance_end_real FROM account_bank_statement "
                    "WHERE journal_id = :jid AND date < :dt AND id <> :sid "
                    "ORDER BY date DESC LIMIT 1"
                ),
                {"jid": rec["journal_id"], "dt": rec["date"], "sid": statement_id},
            )
            prior = prior_row.fetchone()

        if prior is not None:
            prior_end = Decimal(str(prior[0]))
            this_start = Decimal(str(rec["balance_start"] or "0"))
            if abs(prior_end - this_start) >= Decimal("0.01"):
                raise DodooError(
                    f"Statement {statement_id}'s starting balance ({this_start}) does not "
                    f"match the prior statement's ending balance ({prior_end})"
                )

        await super().write(env, [statement_id], {"state": "confirmed"})
        _log.info(
            "account.bank.statement confirmed",
            extra={
                "model": "account.bank.statement",
                "record_id": statement_id,
                "event": "action_confirm",
            },
        )
        return True


class AccountBankStatementLine(BaseModel):
    """One bank-reported transaction on a statement (FR-027/029)."""

    _name = "account.bank.statement.line"

    statement_id = Many2one("account.bank.statement", required=True)
    date = Date(required=True)
    payment_ref = Char(size=256)
    partner_id = Many2one("res.partner")
    amount = Monetary()
    move_line_id = Many2one("account.move.line")

    @classmethod
    async def reconcile_against(
        cls, env: Environment, line_id: int, move_line_ids: list[int]
    ) -> dict[str, Any]:
        """FR-029: reconcile a statement line against one or more posted
        ``account.move.line`` rows summing to its amount. An exact 1:1 match
        sets ``move_line_id`` directly; a 1:N match splits the statement line
        into child lines (one per matched move line) via bulk create, mirroring
        how a bank's own import can produce several lines for one transaction.
        """
        records = await super().read(env, [line_id], ["statement_id", "date", "amount"])
        if not records:
            raise DodooError(f"account.bank.statement.line {line_id} not found")
        rec = records[0]

        async with env.dml_conn() as conn:
            rows = await conn.execute(
                text(
                    "SELECT ml.id, ml.amount_residual FROM account_move_line ml "
                    "JOIN account_move m ON m.id = ml.move_id "
                    "WHERE ml.id = ANY(:ids) AND m.state = 'posted'"
                ),
                {"ids": move_line_ids},
            )
            matched = {r[0]: Decimal(str(r[1])) for r in rows}

        missing = set(move_line_ids) - set(matched)
        if missing:
            raise DodooError(f"Move lines not found or not posted: {sorted(missing)}")

        if len(move_line_ids) == 1:
            await super().write(env, [line_id], {"move_line_id": move_line_ids[0]})
            _log.info(
                "account.bank.statement.line reconciled",
                extra={
                    "model": "account.bank.statement.line",
                    "record_id": line_id,
                    "event": "reconcile_against",
                    "move_line_ids": move_line_ids,
                },
            )
            return {"reconciled": [line_id]}

        # 1:N split: this line's own amount is divided across N child lines,
        # each carrying one matched move line.
        created_ids = []
        async with env.dml_conn() as conn:
            for mlid in move_line_ids:
                child_amount = matched[mlid]
                result = await conn.execute(
                    text(
                        "INSERT INTO account_bank_statement_line "
                        "(statement_id, date, payment_ref, amount, move_line_id, "
                        "create_date, write_date) "
                        "VALUES (:sid, :dt, :ref, :amt, :mlid, now(), now()) RETURNING id"
                    ),
                    {
                        "sid": rec["statement_id"],
                        "dt": rec["date"],
                        "ref": f"Split of statement line {line_id}",
                        "amt": str(child_amount),
                        "mlid": mlid,
                    },
                )
                created_ids.append(result.scalar_one())
            await conn.execute(
                text("DELETE FROM account_bank_statement_line WHERE id = :lid"),
                {"lid": line_id},
            )
            await conn.commit()

        _log.info(
            "account.bank.statement.line split-reconciled",
            extra={
                "model": "account.bank.statement.line",
                "record_id": line_id,
                "event": "reconcile_against",
                "move_line_ids": move_line_ids,
                "created_ids": created_ids,
            },
        )
        return {"reconciled": created_ids}
