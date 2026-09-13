"""Currency-rate lookup, FX conversion at posting, realized gain/loss on
reconciliation, and period-end unrealized revaluation (FR-023/024/025/026,
ADR-042)."""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text


@pytest_asyncio.fixture
async def usd_currency_id(env):
    async with env.dml_conn() as conn:
        row = await conn.execute(text("SELECT id FROM res_currency WHERE code='USD'"))
        r = row.fetchone()
        if r:
            return r[0]
    from dodoo.addons.base.models.res_currency import ResCurrency

    return await ResCurrency.create(
        env, {"code": "USD", "name": "US Dollar", "symbol": "$", "rounding": 2}
    )


@pytest_asyncio.fixture
async def exchange_accounts(env, company_id):
    async with env.dml_conn() as conn:
        income_row = await conn.execute(
            text("SELECT id FROM account_account WHERE code='4100' AND company_id=:cid"),
            {"cid": company_id},
        )
        expense_row = await conn.execute(
            text("SELECT id FROM account_account WHERE code='5200' AND company_id=:cid"),
            {"cid": company_id},
        )
        income_id = income_row.scalar_one()
        expense_id = expense_row.scalar_one()

    from dodoo.addons.base.models.res_company import ResCompany

    await ResCompany.write(
        env,
        [company_id],
        {
            "income_currency_exchange_account_id": income_id,
            "expense_currency_exchange_account_id": expense_id,
        },
    )
    return income_id, expense_id


@pytest.mark.asyncio
async def test_get_rate_returns_latest_on_or_before_date(env, usd_currency_id, currency_id):
    from dodoo.addons.base.models.res_currency import ResCurrencyRate

    await ResCurrencyRate.create(
        env, {"currency_id": usd_currency_id, "rate_date": datetime.date(2026, 1, 1), "rate": Decimal("0.90")}
    )
    await ResCurrencyRate.create(
        env, {"currency_id": usd_currency_id, "rate_date": datetime.date(2026, 2, 1), "rate": Decimal("0.95")}
    )
    rate = await ResCurrencyRate.get_rate(env, usd_currency_id, currency_id, datetime.date(2026, 1, 15))
    assert rate == 0.90
    rate2 = await ResCurrencyRate.get_rate(env, usd_currency_id, currency_id, datetime.date(2026, 3, 1))
    assert rate2 == 0.95


@pytest.mark.asyncio
async def test_get_rate_same_currency_returns_one(env, currency_id):
    from dodoo.addons.base.models.res_currency import ResCurrencyRate

    rate = await ResCurrencyRate.get_rate(env, currency_id, currency_id, datetime.date.today())
    assert rate == 1.0


@pytest.mark.asyncio
async def test_fx_conversion_at_posting(env, company_id, usd_currency_id, journal_sale, revenue_account):
    """FR-024: a foreign-currency line's amount_currency is converted into
    company-currency debit/credit using the rate applicable to the move date."""
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine
    from dodoo.addons.base.models.res_currency import ResCurrencyRate

    await ResCurrencyRate.create(
        env, {"currency_id": usd_currency_id, "rate_date": datetime.date(2026, 1, 1), "rate": Decimal("0.90")}
    )

    move_id = await AccountMove.create(
        env,
        {
            "move_type": "entry",
            "journal_id": journal_sale,
            "company_id": company_id,
            "currency_id": usd_currency_id,
            "date": datetime.date(2026, 1, 1),
        },
    )
    line_id = await AccountMoveLine.create(
        env,
        {
            "move_id": move_id,
            "account_id": revenue_account,
            "date": datetime.date(2026, 1, 1),
            "display_type": "product",
            "currency_id": usd_currency_id,
            "amount_currency": -100,  # credit side (revenue), 100 USD
        },
    )
    # Balance the entry with a matching debit line in company currency terms
    from sqlalchemy import text as _text

    async with env.dml_conn() as conn:
        arow = await conn.execute(_text("SELECT id FROM account_account WHERE code='1000' AND company_id=:cid"), {"cid": company_id})
        ar_id = arow.scalar_one()
        await conn.execute(
            _text(
                "INSERT INTO account_move_line (move_id, account_id, date, display_type, "
                "debit, credit, balance, currency_id, amount_currency, create_date, write_date) "
                "VALUES (:mid, :acct, :dt, 'product', :d, 0, :d, :cur, :ac, now(), now())"
            ),
            {"mid": move_id, "acct": ar_id, "dt": datetime.date(2026, 1, 1), "d": "90.00", "cur": usd_currency_id, "ac": "100"},
        )
        await conn.commit()

    await AccountMove.action_post(env, [move_id])

    rows = await AccountMoveLine.read(env, [line_id], ["debit", "credit"])
    assert Decimal(str(rows[0]["credit"])) == Decimal("90.00")
    assert Decimal(str(rows[0]["debit"])) == Decimal("0")


@pytest.mark.asyncio
async def test_realized_exchange_gain_on_reconciliation(
    env, company_id, currency_id, usd_currency_id, journal_sale, revenue_account,
    ar_account, partner_id, exchange_accounts,
):
    """FR-025: an invoice booked at one rate, paid at a different rate, posts a
    realized exchange gain/loss for the difference."""
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine
    from dodoo.addons.base.models.res_currency import ResCurrencyRate

    await ResCurrencyRate.create(
        env, {"currency_id": usd_currency_id, "rate_date": datetime.date(2026, 1, 1), "rate": Decimal("0.90")}
    )
    await ResCurrencyRate.create(
        env, {"currency_id": usd_currency_id, "rate_date": datetime.date(2026, 2, 1), "rate": Decimal("0.95")}
    )

    invoice_id = await AccountMove.create(
        env,
        {
            "move_type": "out_invoice",
            "journal_id": journal_sale,
            "company_id": company_id,
            "currency_id": usd_currency_id,
            "partner_id": partner_id,
            "date": datetime.date(2026, 1, 1),
            "invoice_date": datetime.date(2026, 1, 1),
        },
    )
    await AccountMoveLine.create(
        env,
        {
            "move_id": invoice_id,
            "account_id": revenue_account,
            "date": datetime.date(2026, 1, 1),
            "display_type": "product",
            "currency_id": usd_currency_id,
            "amount_currency": -100,
        },
    )
    await AccountMove.action_post(env, [invoice_id])

    async with env.dml_conn() as conn:
        inv_line_row = await conn.execute(
            text(
                "SELECT id, amount_residual FROM account_move_line "
                "WHERE move_id=:mid AND display_type='payment_term'"
            ),
            {"mid": invoice_id},
        )
        inv_line = inv_line_row.fetchone()
    inv_line_id, inv_residual = inv_line[0], Decimal(str(inv_line[1]))
    assert inv_residual == Decimal("90.00")  # booked at 0.90

    # Payment booked at the later (0.95) rate for the same 100 USD -> 95.00
    payment_move_id = await AccountMove.create(
        env,
        {
            "move_type": "entry",
            "journal_id": journal_sale,
            "company_id": company_id,
            "currency_id": usd_currency_id,
            "date": datetime.date(2026, 2, 1),
        },
    )
    async with env.dml_conn() as conn:
        await conn.execute(
            text(
                "INSERT INTO account_move_line (move_id, account_id, partner_id, date, "
                "display_type, debit, credit, balance, amount_residual, currency_id, "
                "amount_currency, create_date, write_date) "
                "VALUES (:mid, :acct, :pid, :dt, 'payment_term', 0, :c, :bal, :bal, :cur, :ac, now(), now())"
            ),
            {
                "mid": payment_move_id, "acct": ar_account, "pid": partner_id,
                "dt": datetime.date(2026, 2, 1), "c": "95.00", "bal": "-95.00",
                "cur": usd_currency_id, "ac": "-100",
            },
        )
        bank_row = await conn.execute(
            text("SELECT id FROM account_account WHERE code='1020' AND company_id=:cid"),
            {"cid": company_id},
        )
        await conn.execute(
            text(
                "INSERT INTO account_move_line (move_id, account_id, date, display_type, "
                "debit, credit, balance, create_date, write_date) "
                "VALUES (:mid, :acct, :dt, 'product', :d, 0, :d, now(), now())"
            ),
            {"mid": payment_move_id, "acct": bank_row.scalar_one(), "dt": datetime.date(2026, 2, 1), "d": "95.00"},
        )
        await conn.commit()
    await AccountMove.action_post(env, [payment_move_id])

    async with env.dml_conn() as conn:
        pay_line_row = await conn.execute(
            text(
                "SELECT id FROM account_move_line WHERE move_id=:mid AND display_type='payment_term'"
            ),
            {"mid": payment_move_id},
        )
        pay_line_id = pay_line_row.scalar_one()

    from dodoo.addons.account.models.account_reconcile import AccountPartialReconcile

    result = await AccountPartialReconcile.reconcile_lines(env, inv_line_id, pay_line_id)
    assert result["full_reconcile_id"] is not None
    assert result["fx_move_id"] is not None

    income_account_id, _expense_account_id = exchange_accounts
    async with env.dml_conn() as conn:
        gain_row = await conn.execute(
            text(
                "SELECT debit, credit FROM account_move_line "
                "WHERE move_id=:mid AND account_id=:acct"
            ),
            {"mid": result["fx_move_id"], "acct": income_account_id},
        )
        gain_line = gain_row.fetchone()
    assert gain_line is not None
    # Booked at 0.90 (90.00 receivable) but paid at 0.95 (95.00 received) —
    # the company received 5.00 more than the receivable required: a gain.
    assert Decimal(str(gain_line[1])) - Decimal(str(gain_line[0])) == Decimal("5.00")


@pytest.mark.asyncio
async def test_unrealized_revaluation_posts_and_reverses(
    env, company_id, currency_id, usd_currency_id, journal_sale, revenue_account,
    partner_id, exchange_accounts,
):
    """FR-026: an open foreign-currency receivable gets a revaluation entry at
    the closing rate, plus a draft next-day reversal."""
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine
    from dodoo.addons.base.models.res_currency import ResCurrencyRate

    await ResCurrencyRate.create(
        env, {"currency_id": usd_currency_id, "rate_date": datetime.date(2026, 1, 1), "rate": Decimal("0.90")}
    )

    invoice_id = await AccountMove.create(
        env,
        {
            "move_type": "out_invoice",
            "journal_id": journal_sale,
            "company_id": company_id,
            "currency_id": usd_currency_id,
            "partner_id": partner_id,
            "date": datetime.date(2026, 1, 1),
            "invoice_date": datetime.date(2026, 1, 1),
        },
    )
    await AccountMoveLine.create(
        env,
        {
            "move_id": invoice_id,
            "account_id": revenue_account,
            "date": datetime.date(2026, 1, 1),
            "display_type": "product",
            "currency_id": usd_currency_id,
            "amount_currency": -100,
        },
    )
    await AccountMove.action_post(env, [invoice_id])

    # Closing rate has moved: 1 USD is now worth more company-currency.
    await ResCurrencyRate.create(
        env, {"currency_id": usd_currency_id, "rate_date": datetime.date(2026, 1, 31), "rate": Decimal("1.00")}
    )

    entries = await AccountMove.revalue_currency_balances(
        env, company_id, datetime.date(2026, 1, 31)
    )
    assert len(entries) == 1
    entry = entries[0]

    rows = await AccountMove.read(env, [entry["move_id"]], ["state", "amount_total"])
    assert rows[0]["state"] == "posted"

    rev_rows = await AccountMove.read(env, [entry["reversal_move_id"]], ["state", "date"])
    assert rev_rows[0]["state"] == "draft"
    assert rev_rows[0]["date"] == datetime.date(2026, 2, 1)
