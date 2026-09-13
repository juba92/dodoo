"""account.move.line's analytic_distribution write-guard (FR-038) and the
AccountReportAnalytic roll-up (FR-039), ADR-045 — both exercised here since
this is where `account` and `analytic` coexist installed together."""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from dodoo.core.exceptions import DodooError


@pytest.mark.asyncio
async def test_unknown_analytic_account_id_rejected(env, company_id, revenue_account):
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine

    move_id = await AccountMove.create(
        env,
        {
            "move_type": "entry",
            "journal_id": (await _misc_journal(env, company_id)),
            "company_id": company_id,
            "currency_id": (await _currency(env)),
            "date": datetime.date(2025, 3, 1),
        },
    )
    with pytest.raises(DodooError):
        await AccountMoveLine.create(
            env,
            {
                "move_id": move_id,
                "account_id": revenue_account,
                "date": datetime.date(2025, 3, 1),
                "display_type": "product",
                "credit": 100,
                "analytic_distribution": {"999999": 100},
            },
        )


@pytest.mark.asyncio
async def test_archived_analytic_account_id_rejected(env, company_id, revenue_account):
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine
    from dodoo.addons.analytic.models.analytic_account import AnalyticAccount

    analytic_id = await AnalyticAccount.create(
        env, {"name": "Archived For Test", "company_id": company_id, "active": False}
    )
    move_id = await AccountMove.create(
        env,
        {
            "move_type": "entry",
            "journal_id": (await _misc_journal(env, company_id)),
            "company_id": company_id,
            "currency_id": (await _currency(env)),
            "date": datetime.date(2025, 3, 1),
        },
    )
    with pytest.raises(DodooError):
        await AccountMoveLine.create(
            env,
            {
                "move_id": move_id,
                "account_id": revenue_account,
                "date": datetime.date(2025, 3, 1),
                "display_type": "product",
                "credit": 100,
                "analytic_distribution": {str(analytic_id): 100},
            },
        )


@pytest.mark.asyncio
async def test_percentages_not_summing_to_100_rejected(env, company_id, revenue_account):
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine
    from dodoo.addons.analytic.models.analytic_account import AnalyticAccount

    a1 = await AnalyticAccount.create(env, {"name": "A1", "company_id": company_id})
    a2 = await AnalyticAccount.create(env, {"name": "A2", "company_id": company_id})
    move_id = await AccountMove.create(
        env,
        {
            "move_type": "entry",
            "journal_id": (await _misc_journal(env, company_id)),
            "company_id": company_id,
            "currency_id": (await _currency(env)),
            "date": datetime.date(2025, 3, 1),
        },
    )
    with pytest.raises(DodooError):
        await AccountMoveLine.create(
            env,
            {
                "move_id": move_id,
                "account_id": revenue_account,
                "date": datetime.date(2025, 3, 1),
                "display_type": "product",
                "credit": 100,
                "analytic_distribution": {str(a1): 60, str(a2): 30},
            },
        )


@pytest.mark.asyncio
async def test_valid_distribution_accepted_and_rolls_up(
    env, company_id, currency_id, journal_sale, revenue_account
):
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine
    from dodoo.addons.account.models.account_report import AccountReportAnalytic
    from dodoo.addons.analytic.models.analytic_account import AnalyticAccount

    a1 = await AnalyticAccount.create(env, {"name": "Roll-up A1", "company_id": company_id})
    a2 = await AnalyticAccount.create(env, {"name": "Roll-up A2", "company_id": company_id})

    move_id = await AccountMove.create(
        env,
        {
            "move_type": "entry",
            "journal_id": journal_sale,
            "company_id": company_id,
            "currency_id": currency_id,
            "date": datetime.date(2025, 4, 1),
        },
    )
    await AccountMoveLine.create(
        env,
        {
            "move_id": move_id,
            "account_id": revenue_account,
            "date": datetime.date(2025, 4, 1),
            "display_type": "product",
            "credit": 1000,
            "analytic_distribution": {str(a1): 70, str(a2): 30},
        },
    )
    # Balance the entry.
    from sqlalchemy import text

    async with env.dml_conn() as conn:
        bank_row = await conn.execute(
            text("SELECT id FROM account_account WHERE code='1020' AND company_id=:cid"),
            {"cid": company_id},
        )
        await conn.execute(
            text(
                "INSERT INTO account_move_line "
                "(move_id, account_id, date, display_type, debit, credit, balance, "
                "create_date, write_date) "
                "VALUES (:mid, :acct, :dt, 'product', 1000, 0, 1000, now(), now())"
            ),
            {"mid": move_id, "acct": bank_row.scalar_one(), "dt": datetime.date(2025, 4, 1)},
        )
        await conn.commit()
    await AccountMove.action_post(env, [move_id])

    rep = await AccountReportAnalytic.get_report(
        env, date_from=datetime.date(2025, 4, 1), date_to=datetime.date(2025, 4, 30),
        company_id=company_id,
    )
    by_id = {r["analytic_account_id"]: r for r in rep["lines"]}
    # revenue is a credit-heavy line (balance -1000); 70%/30% split.
    assert Decimal(by_id[a1]["amount"]) == Decimal("-700.00")
    assert Decimal(by_id[a2]["amount"]) == Decimal("-300.00")


async def _misc_journal(env, company_id):
    from sqlalchemy import text

    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT id FROM account_journal WHERE type='general' AND company_id=:cid LIMIT 1"),
            {"cid": company_id},
        )
        return row.scalar_one()


async def _currency(env):
    from sqlalchemy import text

    async with env.dml_conn() as conn:
        row = await conn.execute(text("SELECT id FROM res_currency WHERE code='EUR' LIMIT 1"))
        return row.scalar_one()
