"""Cash-rounding strategies: up/down/half_up methods, add_invoice_line vs
biggest_tax strategies (FR-030, ADR-043)."""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text


@pytest_asyncio.fixture
async def sale_tax_15(env, company_id):
    from dodoo.addons.account.models.account_tax import AccountTax

    return await AccountTax.create(
        env,
        {
            "name": "VAT 15%",
            "type_tax_use": "sale",
            "amount_type": "percent",
            "amount": 15,
            "price_include": False,
            "company_id": company_id,
        },
    )


@pytest_asyncio.fixture
async def rounding_account(env, company_id):
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT id FROM account_account WHERE code='5200' AND company_id=:cid"),
            {"cid": company_id},
        )
        return row.scalar_one()


async def _post_rounded_invoice(
    env, *, company_id, currency_id, journal_sale, revenue_account, sale_tax_15, cash_rounding_id
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
            "date": datetime.date.today(),
            "invoice_cash_rounding_id": cash_rounding_id,
        },
    )
    await AccountMoveLine.create(
        env,
        {
            "move_id": move_id,
            "account_id": revenue_account,
            "date": datetime.date.today(),
            "display_type": "product",
            "price_unit": Decimal("100.03"),
            "quantity": 1,
            "credit": Decimal("100.03"),
            "tax_ids": [sale_tax_15],
        },
    )
    await AccountMove.action_post(env, [move_id])
    return move_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rounding_method", "expected_line_balance"),
    [
        ("half_up", Decimal("-0.02")),  # 115.03 / 0.05 = 2300.6 steps -> round to 2301 -> 115.05
        ("up", Decimal("-0.02")),  # ceiling(2300.6) -> 2301 -> 115.05
        ("down", Decimal("0.03")),  # floor(2300.6) -> 2300 -> 115.00
    ],
)
async def test_add_invoice_line_strategy_by_method(
    env, company_id, currency_id, journal_sale, revenue_account, sale_tax_15,
    rounding_account, rounding_method, expected_line_balance,
):
    from dodoo.addons.account.models.account_cash_rounding import AccountCashRounding

    cash_rounding_id = await AccountCashRounding.create(
        env,
        {
            "name": f"Round to 0.05 ({rounding_method})",
            "rounding": Decimal("0.05"),
            "rounding_method": rounding_method,
            "strategy": "add_invoice_line",
            "account_id": rounding_account,
            "company_id": company_id,
        },
    )
    move_id = await _post_rounded_invoice(
        env, company_id=company_id, currency_id=currency_id, journal_sale=journal_sale,
        revenue_account=revenue_account, sale_tax_15=sale_tax_15,
        cash_rounding_id=cash_rounding_id,
    )

    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT balance FROM account_move_line "
                "WHERE move_id=:mid AND account_id=:acct"
            ),
            {"mid": move_id, "acct": rounding_account},
        )
        rounding_line = row.fetchone()
    assert rounding_line is not None
    assert Decimal(str(rounding_line[0])) == expected_line_balance


@pytest.mark.asyncio
async def test_biggest_tax_strategy_adjusts_tax_line(
    env, company_id, currency_id, journal_sale, revenue_account, sale_tax_15,
):
    from dodoo.addons.account.models.account_cash_rounding import AccountCashRounding

    cash_rounding_id = await AccountCashRounding.create(
        env,
        {
            "name": "Round to 0.05 (biggest tax)",
            "rounding": Decimal("0.05"),
            "rounding_method": "half_up",
            "strategy": "biggest_tax",
            "company_id": company_id,
        },
    )
    move_id = await _post_rounded_invoice(
        env, company_id=company_id, currency_id=currency_id, journal_sale=journal_sale,
        revenue_account=revenue_account, sale_tax_15=sale_tax_15,
        cash_rounding_id=cash_rounding_id,
    )

    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT balance FROM account_move_line "
                "WHERE move_id=:mid AND display_type='tax'"
            ),
            {"mid": move_id},
        )
        tax_line = row.fetchone()
    assert tax_line is not None
    # Original tax was -15.00; the 0.6-step rounds the 115.03 total up to
    # 115.05, adding -0.02 onto the (only, therefore biggest) tax line.
    assert Decimal(str(tax_line[0])) == Decimal("-15.02")
