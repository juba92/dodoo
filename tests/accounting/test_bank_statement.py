"""Bank statement continuity checks and line reconciliation (FR-027/028/029,
ADR-043)."""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from dodoo.core.exceptions import DodooError


@pytest_asyncio.fixture
async def bank_journal(env, company_id):
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT id FROM account_journal WHERE type='bank' AND company_id=:cid LIMIT 1"),
            {"cid": company_id},
        )
        return row.scalar_one()


async def _create_statement(env, *, journal_id, company_id, date, balance_start, balance_end_real):
    from dodoo.addons.account.models.account_bank_statement import AccountBankStatement

    return await AccountBankStatement.create(
        env,
        {
            "journal_id": journal_id,
            "company_id": company_id,
            "date": date,
            "balance_start": balance_start,
            "balance_end_real": balance_end_real,
        },
    )


@pytest.mark.asyncio
async def test_get_status_reports_arithmetic_completeness(env, bank_journal, company_id):
    from dodoo.addons.account.models.account_bank_statement import (
        AccountBankStatement,
        AccountBankStatementLine,
    )

    statement_id = await _create_statement(
        env, journal_id=bank_journal, company_id=company_id,
        date=datetime.date(2026, 1, 31), balance_start=Decimal("1000.00"),
        balance_end_real=Decimal("1250.00"),
    )
    await AccountBankStatementLine.create(
        env,
        {
            "statement_id": statement_id,
            "date": datetime.date(2026, 1, 15),
            "payment_ref": "Deposit",
            "amount": Decimal("250.00"),
        },
    )

    status = await AccountBankStatement.get_status(env, statement_id)
    assert status["complete"] is True
    assert Decimal(status["computed_balance"]) == Decimal("1250.00")


@pytest.mark.asyncio
async def test_action_confirm_rejects_broken_continuity(env, bank_journal, company_id):
    from dodoo.addons.account.models.account_bank_statement import AccountBankStatement

    first_id = await _create_statement(
        env, journal_id=bank_journal, company_id=company_id,
        date=datetime.date(2026, 1, 31), balance_start=Decimal("1000.00"),
        balance_end_real=Decimal("1250.00"),
    )
    await AccountBankStatement.action_confirm(env, first_id)

    # Second statement's balance_start doesn't match the first's balance_end_real.
    second_id = await _create_statement(
        env, journal_id=bank_journal, company_id=company_id,
        date=datetime.date(2026, 2, 28), balance_start=Decimal("1300.00"),
        balance_end_real=Decimal("1400.00"),
    )
    with pytest.raises(DodooError):
        await AccountBankStatement.action_confirm(env, second_id)

    # A correctly-continued statement confirms cleanly.
    third_id = await _create_statement(
        env, journal_id=bank_journal, company_id=company_id,
        date=datetime.date(2026, 3, 31), balance_start=Decimal("1250.00"),
        balance_end_real=Decimal("1500.00"),
    )
    assert await AccountBankStatement.action_confirm(env, third_id) is True


@pytest.mark.asyncio
async def test_reconcile_against_one_to_one_and_one_to_many(
    env, bank_journal, company_id, journal_sale, partner_id
):
    from dodoo.addons.account.models.account_bank_statement import (
        AccountBankStatementLine,
    )
    from dodoo.addons.account.models.account_move import AccountMove

    statement_id = await _create_statement(
        env, journal_id=bank_journal, company_id=company_id,
        date=datetime.date(2026, 1, 31), balance_start=Decimal("0.00"),
        balance_end_real=Decimal("150.00"),
    )

    async with env.dml_conn() as conn:
        ar_row = await conn.execute(
            text(
                "SELECT id FROM account_account WHERE account_type='asset_receivable' "
                "AND company_id=:cid"
            ),
            {"cid": company_id},
        )
        ar_account_id = ar_row.scalar_one()
        bank_row = await conn.execute(
            text("SELECT id FROM account_account WHERE code='1020' AND company_id=:cid"),
            {"cid": company_id},
        )
        bank_account_id = bank_row.scalar_one()

    async def _post_receipt(amount: Decimal) -> int:
        move_id = await AccountMove.create(
            env,
            {
                "move_type": "entry",
                "journal_id": journal_sale,
                "company_id": company_id,
                "date": datetime.date(2026, 1, 10),
            },
        )
        async with env.dml_conn() as conn:
            ml_row = await conn.execute(
                text(
                    "INSERT INTO account_move_line "
                    "(move_id, account_id, partner_id, date, display_type, debit, credit, "
                    "balance, amount_residual, create_date, write_date) "
                    "VALUES (:mid, :acct, :pid, :dt, 'payment_term', 0, :amt, :bal, :bal, "
                    "now(), now()) RETURNING id"
                ),
                {
                    "mid": move_id, "acct": ar_account_id, "pid": partner_id,
                    "dt": datetime.date(2026, 1, 10), "amt": str(amount), "bal": str(-amount),
                },
            )
            ar_line_id = ml_row.scalar_one()
            await conn.execute(
                text(
                    "INSERT INTO account_move_line "
                    "(move_id, account_id, date, display_type, debit, credit, balance, "
                    "create_date, write_date) "
                    "VALUES (:mid, :acct, :dt, 'product', :amt, 0, :amt, now(), now())"
                ),
                {
                    "mid": move_id, "acct": bank_account_id,
                    "dt": datetime.date(2026, 1, 10), "amt": str(amount),
                },
            )
            await conn.commit()
        await AccountMove.action_post(env, [move_id])
        return ar_line_id

    # 1:1 — one statement line matched to one move line.
    move_line_a = await _post_receipt(Decimal("50.00"))
    stmt_line_a = await AccountBankStatementLine.create(
        env,
        {
            "statement_id": statement_id, "date": datetime.date(2026, 1, 10),
            "payment_ref": "Receipt A", "amount": Decimal("50.00"),
        },
    )
    result_a = await AccountBankStatementLine.reconcile_against(env, stmt_line_a, [move_line_a])
    assert result_a["reconciled"] == [stmt_line_a]
    updated = await AccountBankStatementLine.read(env, [stmt_line_a], ["move_line_id"])
    assert updated[0]["move_line_id"] == move_line_a

    # 1:N — one statement line's amount splits across two matched move lines.
    move_line_b = await _post_receipt(Decimal("60.00"))
    move_line_c = await _post_receipt(Decimal("40.00"))
    stmt_line_bc = await AccountBankStatementLine.create(
        env,
        {
            "statement_id": statement_id, "date": datetime.date(2026, 1, 20),
            "payment_ref": "Receipt B+C", "amount": Decimal("100.00"),
        },
    )
    result_bc = await AccountBankStatementLine.reconcile_against(
        env, stmt_line_bc, [move_line_b, move_line_c]
    )
    assert len(result_bc["reconciled"]) == 2

    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT id FROM account_bank_statement_line WHERE id=:lid"
            ),
            {"lid": stmt_line_bc},
        )
        assert row.fetchone() is None  # split parent line removed
