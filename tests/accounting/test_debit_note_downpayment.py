"""Debit notes (increase the amount owed on a posted bill/invoice) and down
payments (tracked and netted against their final invoice) — FR-011/012,
ADR-040."""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest


@pytest.mark.asyncio
async def test_debit_note_creation_increases_amount_owed(
    env, company_id, currency_id, journal_sale, ar_account, revenue_account
):
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine

    move_id = await AccountMove.create(
        env,
        {
            "move_type": "out_invoice",
            "journal_id": journal_sale,
            "company_id": company_id,
            "currency_id": currency_id,
            "date": datetime.date(2025, 1, 10),
        },
    )
    await AccountMoveLine.create(
        env,
        {
            "move_id": move_id,
            "account_id": revenue_account,
            "date": datetime.date(2025, 1, 10),
            "display_type": "product",
            "price_unit": 300,
            "quantity": 1,
            "credit": 300,
        },
    )
    await AccountMove.action_post(env, [move_id])

    debit_note_id = await AccountMove.action_create_debit_note(env, move_id)
    rows = await AccountMove.read(
        env, [debit_note_id], ["move_type", "debit_origin_id", "state"]
    )
    assert rows[0]["move_type"] == "out_invoice"  # same type, not a refund
    assert rows[0]["debit_origin_id"] == move_id
    assert rows[0]["state"] == "draft"

    from sqlalchemy import text

    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT price_unit, quantity FROM account_move_line "
                "WHERE move_id=:mid AND display_type='product'"
            ),
            {"mid": debit_note_id},
        )
        line_rows = row.fetchall()
    assert len(line_rows) == 1
    assert Decimal(str(line_rows[0][0])) == Decimal("300")
    assert Decimal(str(line_rows[0][1])) == Decimal("1")

    # Posting the debit note creates a SEPARATE, additional amount owed —
    # not a netting/reversal against the original.
    await AccountMove.action_post(env, [debit_note_id])
    debit_note_row = await AccountMove.read(env, [debit_note_id], ["amount_total"])
    assert Decimal(str(debit_note_row[0]["amount_total"])) == Decimal("300.00")

    orig_row = await AccountMove.read(env, [move_id], ["amount_total"])
    assert Decimal(str(orig_row[0]["amount_total"])) == Decimal("300.00")  # unchanged


@pytest.mark.asyncio
async def test_down_payment_nets_against_final_invoice(
    env, company_id, currency_id, journal_sale, ar_account, revenue_account
):
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine

    final_invoice_id = await AccountMove.create(
        env,
        {
            "move_type": "out_invoice",
            "journal_id": journal_sale,
            "company_id": company_id,
            "currency_id": currency_id,
            "date": datetime.date(2025, 2, 1),
        },
    )
    await AccountMoveLine.create(
        env,
        {
            "move_id": final_invoice_id,
            "account_id": revenue_account,
            "date": datetime.date(2025, 2, 1),
            "display_type": "product",
            "price_unit": 1000,
            "quantity": 1,
            "credit": 1000,
        },
    )

    down_payment_id = await AccountMove.create(
        env,
        {
            "move_type": "out_invoice",
            "journal_id": journal_sale,
            "company_id": company_id,
            "currency_id": currency_id,
            "date": datetime.date(2025, 1, 15),
            "down_payment_origin_id": final_invoice_id,
        },
    )
    await AccountMoveLine.create(
        env,
        {
            "move_id": down_payment_id,
            "account_id": revenue_account,
            "date": datetime.date(2025, 1, 15),
            "display_type": "product",
            "price_unit": 200,
            "quantity": 1,
            "credit": 200,
        },
    )
    await AccountMove.action_post(env, [down_payment_id])

    await AccountMove.action_post(env, [final_invoice_id])

    rows = await AccountMove.read(
        env, [final_invoice_id], ["amount_total", "amount_untaxed"]
    )
    assert Decimal(str(rows[0]["amount_untaxed"])) == Decimal("1000.00")
    # 1000 gross less the 200 down payment already collected.
    assert Decimal(str(rows[0]["amount_total"])) == Decimal("800.00")

    from sqlalchemy import text

    async with env.dml_conn() as conn:
        pt_row = await conn.execute(
            text(
                "SELECT balance FROM account_move_line "
                "WHERE move_id=:mid AND display_type='payment_term'"
            ),
            {"mid": final_invoice_id},
        )
        payment_term_balance = Decimal(str(pt_row.scalar_one()))
        dp_row = await conn.execute(
            text(
                "SELECT balance FROM account_move_line "
                "WHERE move_id=:mid AND display_type='down_payment'"
            ),
            {"mid": final_invoice_id},
        )
        down_payment_balance = Decimal(str(dp_row.scalar_one()))

    assert payment_term_balance == Decimal("800.00")
    assert down_payment_balance == Decimal("200.00")
