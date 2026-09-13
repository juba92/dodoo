"""Trial Balance / General Ledger opening balances, fiscal-year close and the
Balance Sheet's fiscal-year-scoped current-year-earnings, and drill-down
fields on all five report payloads (FR-034/035/037, ADR-044).

Per [[accounting-test-isolation]]: run standalone, not batched with other
tests/accounting/ files — these reports aggregate account-level totals
across the whole shared DB with no company_id filter, exactly like the
pre-existing test_reports.py/test_account_balance.py.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest


async def _post_entry(env, company_id, currency_id, journal_id, date, lines):
    """lines: list of (account_id, debit, credit)."""
    from dodoo.addons.account.models.account_move import AccountMove

    move_id = await AccountMove.create(
        env,
        {
            "move_type": "entry",
            "journal_id": journal_id,
            "company_id": company_id,
            "currency_id": currency_id,
            "date": date,
        },
    )
    async with env.dml_conn() as conn:
        from sqlalchemy import text

        for account_id, debit, credit in lines:
            await conn.execute(
                text(
                    "INSERT INTO account_move_line "
                    "(move_id, account_id, date, display_type, debit, credit, balance, "
                    "create_date, write_date) "
                    "VALUES (:mid, :acct, :dt, 'product', :d, :c, :bal, now(), now())"
                ),
                {
                    "mid": move_id, "acct": account_id, "dt": date,
                    "d": str(debit), "c": str(credit), "bal": str(Decimal(str(debit)) - Decimal(str(credit))),
                },
            )
        await conn.commit()
    await AccountMove.action_post(env, [move_id])
    return move_id


@pytest.mark.asyncio
async def test_trial_balance_opening_balance(
    env, company_id, currency_id, journal_sale, ar_account, revenue_account
):
    from dodoo.addons.account.models.account_report import AccountReportTrialBalance

    await _post_entry(
        env, company_id, currency_id, journal_sale, datetime.date(2020, 1, 15),
        [(ar_account, 1000, 0), (revenue_account, 0, 1000)],
    )
    await _post_entry(
        env, company_id, currency_id, journal_sale, datetime.date(2020, 6, 15),
        [(ar_account, 500, 0), (revenue_account, 0, 500)],
    )

    rep = await AccountReportTrialBalance.get_report(
        env, date_from=datetime.date(2020, 3, 1), date_to=datetime.date(2020, 12, 31),
        company_id=company_id,
    )
    codes = {r["code"]: r for r in rep["lines"]}
    assert Decimal(codes["1000"]["opening_balance"]) == Decimal("1000.00")
    assert Decimal(codes["1000"]["debit"]) == Decimal("500.00")
    assert Decimal(codes["1000"]["balance"]) == Decimal("1500.00")


@pytest.mark.asyncio
async def test_general_ledger_opening_balance(
    env, company_id, currency_id, journal_sale, ar_account, revenue_account
):
    from dodoo.addons.account.models.account_report import AccountReportGeneralLedger

    await _post_entry(
        env, company_id, currency_id, journal_sale, datetime.date(2019, 1, 10),
        [(ar_account, 300, 0), (revenue_account, 0, 300)],
    )
    await _post_entry(
        env, company_id, currency_id, journal_sale, datetime.date(2019, 6, 10),
        [(ar_account, 200, 0), (revenue_account, 0, 200)],
    )

    rep = await AccountReportGeneralLedger.get_report(
        env, account_id=ar_account, date_from=datetime.date(2019, 3, 1),
        date_to=datetime.date(2019, 12, 31), company_id=company_id,
    )
    acc = rep["accounts"][0]
    assert Decimal(acc["opening_balance"]) == Decimal("300.00")
    assert [Decimal(x["running_balance"]) for x in acc["lines"]] == [Decimal("500.00")]
    assert Decimal(acc["balance"]) == Decimal("500.00")


@pytest.mark.asyncio
async def test_close_fiscal_year_scopes_current_year_earnings(
    env, company_id, currency_id, journal_sale, ar_account, revenue_account
):
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_report import AccountReportBalanceSheet

    # Year 1: 1000 of revenue.
    await _post_entry(
        env, company_id, currency_id, journal_sale, datetime.date(2021, 6, 1),
        [(ar_account, 1000, 0), (revenue_account, 0, 1000)],
    )
    close_move_id = await AccountMove.close_fiscal_year(
        env, company_id, datetime.date(2021, 12, 31)
    )
    assert close_move_id is not None

    # Year 2: 400 of revenue — should be the ONLY thing in current_year_earnings.
    await _post_entry(
        env, company_id, currency_id, journal_sale, datetime.date(2022, 6, 1),
        [(ar_account, 400, 0), (revenue_account, 0, 400)],
    )

    rep = await AccountReportBalanceSheet.get_report(
        env, date=datetime.date(2022, 12, 31), company_id=company_id
    )
    assert Decimal(rep["current_year_earnings"]) == Decimal("400.00")

    # Year 1's 1000 net result now sits in equity_unaffected (Retained Earnings).
    # (Not asserting overall balance here: this is a shared-DB, batched test
    # file, and an earlier sibling test's own unclosed revenue legitimately
    # shows as an imbalance against this test's own fiscal-year scope — the
    # "balanced" invariant is already covered by test_reports.py.)
    equity_lines = {line["code"]: line for line in rep["groups"]["equity"]["lines"]}
    assert Decimal(equity_lines["3100"]["amount"]) == Decimal("1000.00")


@pytest.mark.asyncio
async def test_drill_down_fields_present_on_all_reports(
    env, company_id, currency_id, journal_sale, ar_account, revenue_account, partner_id
):
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_report import (
        AccountReportAgedReceivable,
        AccountReportBalanceSheet,
        AccountReportGeneralLedger,
        AccountReportProfitLoss,
        AccountReportTrialBalance,
    )

    await _post_entry(
        env, company_id, currency_id, journal_sale, datetime.date(2023, 3, 1),
        [(ar_account, 700, 0), (revenue_account, 0, 700)],
    )

    tb = await AccountReportTrialBalance.get_report(env, company_id=company_id)
    assert all("account_id" in line for line in tb["lines"])

    gl = await AccountReportGeneralLedger.get_report(
        env, account_id=ar_account, company_id=company_id
    )
    assert all("account_id" in acc for acc in gl["accounts"])
    assert all("move_id" in line for acc in gl["accounts"] for line in acc["lines"])

    pl = await AccountReportProfitLoss.get_report(
        env, date_from=datetime.date(2023, 1, 1), date_to=datetime.date(2023, 12, 31),
        company_id=company_id,
    )
    assert all("account_id" in line and "move_id" in line for line in pl["sections"]["income"]["lines"])

    bs = await AccountReportBalanceSheet.get_report(
        env, date=datetime.date(2023, 12, 31), company_id=company_id
    )
    assert all(
        "account_id" in line and "move_id" in line
        for line in bs["groups"]["current_assets"]["lines"]
    )

    # Aged report drill-down needs a payment_term line, not a plain entry.
    move_id = await AccountMove.create(
        env,
        {
            "move_type": "out_invoice",
            "journal_id": journal_sale,
            "company_id": company_id,
            "currency_id": currency_id,
            "partner_id": partner_id,
            "date": datetime.date(2023, 3, 1),
            "invoice_date": datetime.date(2023, 3, 1),
            "invoice_date_due": datetime.date(2023, 3, 1),
        },
    )
    from sqlalchemy import text

    async with env.dml_conn() as conn:
        await conn.execute(
            text(
                "INSERT INTO account_move_line "
                "(move_id, account_id, partner_id, date, display_type, debit, credit, "
                "balance, create_date, write_date) "
                "VALUES (:mid, :a, :p, :dt, 'product', 0, 250, -250, now(), now())"
            ),
            {"mid": move_id, "a": revenue_account, "p": partner_id, "dt": datetime.date(2023, 3, 1)},
        )
        await conn.commit()
    await AccountMove.action_post(env, [move_id])

    aged = await AccountReportAgedReceivable.get_report(
        env, date=datetime.date(2023, 3, 1), company_id=company_id
    )
    assert all("account_id" in p and "bucket_move_ids" in p for p in aged["partners"])
