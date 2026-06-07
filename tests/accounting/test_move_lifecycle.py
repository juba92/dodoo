"""State lifecycle tests: draft→posted, resets, reversals, immutability."""
from __future__ import annotations

import datetime

import pytest

from dodoo.core.exceptions import DodooError


@pytest.mark.asyncio
async def test_draft_to_posted(
    env, company_id, currency_id, journal_sale, ar_account, revenue_account
):
    from sqlalchemy import text

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
        for acct, debit, credit in [(ar_account, 1000, 0), (revenue_account, 0, 1000)]:
            await conn.execute(
                text(
                    "INSERT INTO account_move_line "
                    "(move_id, account_id, date, display_type, debit, credit, balance, create_date, write_date) "
                    "VALUES (:mid, :acct, :dt, 'product', :d, :c, :b, now(), now())"
                ),
                {"mid": move_id, "acct": acct, "dt": today, "d": debit, "c": credit, "b": debit - credit},
            )
        await conn.commit()

    await AccountMove.action_post(env, [move_id])
    recs = await AccountMove.read(env, [move_id], ["state"])
    assert recs[0]["state"] == "posted"


@pytest.mark.asyncio
async def test_posted_write_locked_fields_rejected(
    env, company_id, currency_id, journal_sale, ar_account, revenue_account
):
    from sqlalchemy import text

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
        for acct, debit, credit in [(ar_account, 500, 0), (revenue_account, 0, 500)]:
            await conn.execute(
                text(
                    "INSERT INTO account_move_line "
                    "(move_id, account_id, date, display_type, debit, credit, balance, create_date, write_date) "
                    "VALUES (:mid, :acct, :dt, 'product', :d, :c, :b, now(), now())"
                ),
                {"mid": move_id, "acct": acct, "dt": today, "d": debit, "c": credit, "b": debit - credit},
            )
        await conn.commit()

    await AccountMove.action_post(env, [move_id])

    with pytest.raises(DodooError, match="posted"):
        await AccountMove.write(env, [move_id], {"journal_id": journal_sale + 999})


@pytest.mark.asyncio
async def test_posted_move_cannot_be_deleted(
    env, company_id, currency_id, journal_sale, ar_account, revenue_account
):
    from sqlalchemy import text

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
        for acct, debit, credit in [(ar_account, 200, 0), (revenue_account, 0, 200)]:
            await conn.execute(
                text(
                    "INSERT INTO account_move_line "
                    "(move_id, account_id, date, display_type, debit, credit, balance, create_date, write_date) "
                    "VALUES (:mid, :acct, :dt, 'product', :d, :c, :b, now(), now())"
                ),
                {"mid": move_id, "acct": acct, "dt": today, "d": debit, "c": credit, "b": debit - credit},
            )
        await conn.commit()

    await AccountMove.action_post(env, [move_id])

    with pytest.raises(DodooError, match="posted"):
        await AccountMove.unlink(env, [move_id])


@pytest.mark.asyncio
async def test_system_lines_cannot_be_created_directly(env, ar_account):
    from dodoo.addons.account.models.account_move_line import AccountMoveLine

    with pytest.raises(DodooError, match="system-generated"):
        await AccountMoveLine.create(
            env,
            {
                "move_id": 1,
                "account_id": ar_account,
                "date": datetime.date.today(),
                "display_type": "tax",
                "debit": 100,
                "credit": 0,
            },
        )
