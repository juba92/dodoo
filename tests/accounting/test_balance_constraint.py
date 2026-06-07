"""Critical path: balance constraint enforcement on action_post."""
from __future__ import annotations

import datetime

import pytest

from dodoo.core.exceptions import DodooError


@pytest.mark.asyncio
async def test_post_fails_on_empty_move(env, company_id, currency_id, journal_sale):
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
    with pytest.raises(DodooError, match="no accounting lines"):
        await AccountMove.action_post(env, [move_id])


@pytest.mark.asyncio
async def test_post_fails_on_imbalance(
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

    # Insert imbalanced lines directly (bypassing create guard to test action_post)
    async with env.dml_conn() as conn:
        await conn.execute(
            text(
                "INSERT INTO account_move_line "
                "(move_id, account_id, date, display_type, debit, credit, balance, create_date, write_date) "
                "VALUES (:mid, :acct, :dt, 'product', 500, 0, 500, now(), now())"
            ),
            {"mid": move_id, "acct": ar_account, "dt": datetime.date.today()},
        )
        # Intentionally missing the credit side
        await conn.commit()

    with pytest.raises(DodooError, match="not balanced"):
        await AccountMove.action_post(env, [move_id])


@pytest.mark.asyncio
async def test_post_succeeds_on_balanced_entry(
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
        await conn.execute(
            text(
                "INSERT INTO account_move_line "
                "(move_id, account_id, date, display_type, debit, credit, balance, create_date, write_date) "
                "VALUES (:mid, :acct, :dt, 'product', 1000, 0, 1000, now(), now())"
            ),
            {"mid": move_id, "acct": ar_account, "dt": today},
        )
        await conn.execute(
            text(
                "INSERT INTO account_move_line "
                "(move_id, account_id, date, display_type, debit, credit, balance, create_date, write_date) "
                "VALUES (:mid, :acct, :dt, 'product', 0, 1000, -1000, now(), now())"
            ),
            {"mid": move_id, "acct": revenue_account, "dt": today},
        )
        await conn.commit()

    result = await AccountMove.action_post(env, [move_id])
    assert result is True

    records = await AccountMove.read(env, [move_id], ["state", "name"])
    assert records[0]["state"] == "posted"
    assert records[0]["name"].startswith("INV/")
