"""Financial reports — Trial Balance / GL / P&L / Balance Sheet / Aged (spec US-8, FR-036…040)."""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import text


async def _post_manual(env, company_id, currency_id, journal, rows):
    """Post a balanced journal entry; `rows` = [(account_id, debit, credit), …]."""
    from dodoo.addons.account.models.account_move import AccountMove

    move_id = await AccountMove.create(
        env,
        {
            "move_type": "entry",
            "journal_id": journal,
            "company_id": company_id,
            "currency_id": currency_id,
            "date": datetime.date.today(),
        },
    )
    today = datetime.date.today()
    async with env.dml_conn() as conn:
        for acct, debit, credit in rows:
            await conn.execute(
                text(
                    "INSERT INTO account_move_line "
                    "(move_id, account_id, date, display_type, debit, credit, balance, "
                    " create_date, write_date) "
                    "VALUES (:mid, :a, :dt, 'product', :d, :c, :b, now(), now())"
                ),
                {"mid": move_id, "a": acct, "dt": today, "d": debit, "c": credit, "b": debit - credit},
            )
        await conn.commit()
    await AccountMove.action_post(env, [move_id])
    return move_id


@pytest.fixture
async def _expense_account(env, company_id):
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT id FROM account_account WHERE code='5100' AND company_id=:c"),
            {"c": company_id},
        )
        return row.scalar_one()


@pytest.mark.asyncio
async def test_trial_balance_balanced_and_summed(
    env, company_id, currency_id, journal_sale, ar_account, revenue_account
):
    from dodoo.addons.account.models.account_report import AccountReportTrialBalance

    await _post_manual(env, company_id, currency_id, journal_sale,
                       [(ar_account, 1000, 0), (revenue_account, 0, 1000)])
    await _post_manual(env, company_id, currency_id, journal_sale,
                       [(ar_account, 500, 0), (revenue_account, 0, 500)])

    rep = await AccountReportTrialBalance.get_report(env)
    codes = {r["code"]: r for r in rep["lines"]}
    assert float(codes["1000"]["debit"]) == 1500.0
    assert float(codes["4000"]["credit"]) == 1500.0
    assert float(rep["totals"]["debit"]) == float(rep["totals"]["credit"]) == 1500.0
    assert rep["totals"]["balanced"] is True


@pytest.mark.asyncio
async def test_general_ledger_groups_by_account_with_running_balance(
    env, company_id, currency_id, journal_sale, ar_account, revenue_account
):
    from dodoo.addons.account.models.account_report import AccountReportGeneralLedger

    await _post_manual(env, company_id, currency_id, journal_sale,
                       [(ar_account, 300, 0), (revenue_account, 0, 300)])
    await _post_manual(env, company_id, currency_id, journal_sale,
                       [(ar_account, 200, 0), (revenue_account, 0, 200)])

    rep = await AccountReportGeneralLedger.get_report(env, account_id=ar_account)
    assert len(rep["accounts"]) == 1
    acc = rep["accounts"][0]
    assert [float(x["running_balance"]) for x in acc["lines"]] == [300.0, 500.0]
    assert float(acc["balance"]) == 500.0


@pytest.mark.asyncio
async def test_profit_loss_income_positive_net_computed(
    env, company_id, currency_id, journal_sale, ar_account, revenue_account, _expense_account
):
    from dodoo.addons.account.models.account_report import AccountReportProfitLoss

    await _post_manual(env, company_id, currency_id, journal_sale,
                       [(ar_account, 1000, 0), (revenue_account, 0, 1000)])
    await _post_manual(env, company_id, currency_id, journal_sale,
                       [(_expense_account, 400, 0), (ar_account, 0, 400)])

    rep = await AccountReportProfitLoss.get_report(env)
    s = rep["sections"]
    assert float(s["income"]["total"]) == 1000.0     # shown positive despite credit balance
    assert float(s["expenses"]["total"]) == 400.0
    assert float(s["net_profit"]) == 600.0


@pytest.mark.asyncio
async def test_balance_sheet_balances_with_current_year_earnings(
    env, company_id, currency_id, journal_sale, ar_account, revenue_account
):
    from dodoo.addons.account.models.account_report import AccountReportBalanceSheet

    # Revenue booked to AR: assets +1000, income +1000 → equity via current-year earnings.
    await _post_manual(env, company_id, currency_id, journal_sale,
                       [(ar_account, 1000, 0), (revenue_account, 0, 1000)])

    rep = await AccountReportBalanceSheet.get_report(env)
    assert float(rep["current_year_earnings"]) == 1000.0
    assert float(rep["totals"]["assets"]) == float(rep["totals"]["liabilities_and_equity"])
    assert rep["totals"]["balanced"] is True


@pytest.mark.asyncio
async def test_aged_receivable_buckets_by_due_date(
    env, company_id, currency_id, journal_sale, revenue_account, partner_id
):
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_report import AccountReportAgedReceivable

    today = datetime.date.today()
    move_id = await AccountMove.create(
        env,
        {
            "move_type": "out_invoice",
            "journal_id": journal_sale,
            "company_id": company_id,
            "currency_id": currency_id,
            "partner_id": partner_id,
            "date": today - datetime.timedelta(days=75),
            "invoice_date": today - datetime.timedelta(days=75),
            "invoice_date_due": today - datetime.timedelta(days=75),
        },
    )
    async with env.dml_conn() as conn:
        await conn.execute(
            text(
                "INSERT INTO account_move_line "
                "(move_id, account_id, partner_id, date, display_type, debit, credit, balance, "
                " create_date, write_date) "
                "VALUES (:mid, :a, :p, :dt, 'product', 0, 900, -900, now(), now())"
            ),
            {"mid": move_id, "a": revenue_account, "p": partner_id, "dt": today - datetime.timedelta(days=75)},
        )
        await conn.commit()
    await AccountMove.action_post(env, [move_id])

    rep = await AccountReportAgedReceivable.get_report(env, date=today)
    assert float(rep["totals"]["b_61_90"]) == 900.0
    assert float(rep["totals"]["total"]) == 900.0
    assert rep["partners"] and float(rep["partners"][0]["b_61_90"]) == 900.0
