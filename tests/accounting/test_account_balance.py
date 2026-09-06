"""AccountAccount.get_balance — the debit/credit/net box on the Chart of Accounts form (US-5 AC-5)."""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import text


async def _posted_move(env, company_id, currency_id, journal_sale, ar_account, revenue_account, amount):
    from dodoo.addons.account.models.account_move import AccountMove

    move_id = await AccountMove.create(
        env,
        {
            "move_type": "out_invoice",
            "journal_id": journal_sale,
            "company_id": company_id,
            "currency_id": currency_id,
            "date": datetime.date.today(),
        },
    )
    today = datetime.date.today()
    async with env.dml_conn() as conn:
        for acct, debit, credit in [(ar_account, amount, 0), (revenue_account, 0, amount)]:
            await conn.execute(
                text(
                    "INSERT INTO account_move_line "
                    "(move_id, account_id, date, display_type, debit, credit, balance, "
                    " create_date, write_date) "
                    "VALUES (:mid, :acct, :dt, 'product', :d, :c, :b, now(), now())"
                ),
                {"mid": move_id, "acct": acct, "dt": today, "d": debit, "c": credit, "b": debit - credit},
            )
        await conn.commit()
    await AccountMove.action_post(env, [move_id])
    return move_id


@pytest.mark.asyncio
async def test_get_balance_sums_only_posted_lines(
    env, company_id, currency_id, journal_sale, ar_account, revenue_account
):
    from dodoo.addons.account.models.account_account import AccountAccount

    await _posted_move(env, company_id, currency_id, journal_sale, ar_account, revenue_account, 1000)
    await _posted_move(env, company_id, currency_id, journal_sale, ar_account, revenue_account, 250)

    bal = await AccountAccount.get_balance(env, ar_account)
    assert float(bal["debit"]) == 1250.0
    assert float(bal["credit"]) == 0.0
    assert float(bal["net"]) == 1250.0

    rev = await AccountAccount.get_balance(env, revenue_account)
    assert float(rev["credit"]) == 1250.0
    assert float(rev["net"]) == -1250.0


@pytest.mark.asyncio
async def test_get_balance_zero_for_unused_account(env, company_id):
    from dodoo.addons.account.models.account_account import AccountAccount

    acct_id = await AccountAccount.create(
        env,
        {"code": "9999", "name": "Unused", "account_type": "expense", "company_id": company_id},
    )
    bal = await AccountAccount.get_balance(env, acct_id)
    assert float(bal["debit"]) == 0.0
    assert float(bal["credit"]) == 0.0
    assert float(bal["net"]) == 0.0
