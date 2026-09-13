"""Discount-net tax base, price-included extraction, and per-company rounding
method (FR-010/013/014/015, ADR-040)."""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text


async def _tax_account_id(env, company_id):
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT id FROM account_account WHERE code='2500' AND company_id=:cid"),
            {"cid": company_id},
        )
        return row.scalar_one()


async def _add_tax_repartition_line(env, tax_id, company_id):
    """Every tax needs a `tax`-type repartition line with an account, or
    `_compute_tax_lines` has nowhere to post it and silently skips the line."""
    from dodoo.addons.account.models.account_tax import AccountTaxRepartitionLine

    account_id = await _tax_account_id(env, company_id)
    await AccountTaxRepartitionLine.create(
        env,
        {
            "tax_id": tax_id,
            "document_type": "invoice",
            "repartition_type": "base",
            "factor_percent": 100,
            "sequence": 1,
        },
    )
    await AccountTaxRepartitionLine.create(
        env,
        {
            "tax_id": tax_id,
            "document_type": "invoice",
            "repartition_type": "tax",
            "factor_percent": 100,
            "account_id": account_id,
            "sequence": 2,
        },
    )


@pytest_asyncio.fixture
async def sale_tax_15(env, company_id):
    from dodoo.addons.account.models.account_tax import AccountTax

    tax_id = await AccountTax.create(
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
    await _add_tax_repartition_line(env, tax_id, company_id)
    return tax_id


@pytest_asyncio.fixture
async def sale_tax_15_incl(env, company_id):
    from dodoo.addons.account.models.account_tax import AccountTax

    tax_id = await AccountTax.create(
        env,
        {
            "name": "VAT 15% (incl.)",
            "type_tax_use": "sale",
            "amount_type": "percent",
            "amount": 15,
            "price_include": True,
            "company_id": company_id,
        },
    )
    await _add_tax_repartition_line(env, tax_id, company_id)
    return tax_id


@pytest_asyncio.fixture
async def draft_invoice(env, company_id, currency_id, journal_sale):
    from dodoo.addons.account.models.account_move import AccountMove

    return await AccountMove.create(
        env,
        {
            "move_type": "out_invoice",
            "journal_id": journal_sale,
            "company_id": company_id,
            "currency_id": currency_id,
            "date": datetime.date.today(),
        },
    )


@pytest.mark.asyncio
async def test_tax_computed_on_discounted_base(env, draft_invoice, revenue_account, sale_tax_15):
    """FR-010/013: a 10% discount on a 100 unit line reduces the taxable base to 90."""
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine

    await AccountMoveLine.create(
        env,
        {
            "move_id": draft_invoice,
            "account_id": revenue_account,
            "date": datetime.date.today(),
            "display_type": "product",
            "price_unit": 100,
            "quantity": 1,
            "discount": 10,
            "credit": 90,
            "tax_ids": [sale_tax_15],
        },
    )
    await AccountMove.action_post(env, [draft_invoice])

    rows = await AccountMove.read(
        env, [draft_invoice], ["amount_untaxed", "amount_tax", "amount_total"]
    )
    assert Decimal(str(rows[0]["amount_untaxed"])) == Decimal("90.00")
    assert Decimal(str(rows[0]["amount_tax"])) == Decimal("13.50")
    assert Decimal(str(rows[0]["amount_total"])) == Decimal("103.50")


@pytest.mark.asyncio
async def test_price_included_tax_extracted_from_gross(
    env, draft_invoice, revenue_account, sale_tax_15_incl
):
    """FR-014: price_unit=115 with a 15% price-included tax nets to 100 + 15 tax,
    not 115 + 115*0.15."""
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine

    line_id = await AccountMoveLine.create(
        env,
        {
            "move_id": draft_invoice,
            "account_id": revenue_account,
            "date": datetime.date.today(),
            "display_type": "product",
            "price_unit": 115,
            "quantity": 1,
            "credit": 115,
            "tax_ids": [sale_tax_15_incl],
        },
    )
    await AccountMove.action_post(env, [draft_invoice])

    line_rows = await AccountMoveLine.read(env, [line_id], ["price_subtotal", "credit"])
    assert Decimal(str(line_rows[0]["price_subtotal"])) == Decimal("100.00")
    assert Decimal(str(line_rows[0]["credit"])) == Decimal("100.00")

    rows = await AccountMove.read(
        env, [draft_invoice], ["amount_untaxed", "amount_tax", "amount_total"]
    )
    assert Decimal(str(rows[0]["amount_untaxed"])) == Decimal("100.00")
    assert Decimal(str(rows[0]["amount_tax"])) == Decimal("15.00")
    assert Decimal(str(rows[0]["amount_total"])) == Decimal("115.00")


async def _two_line_invoice_with_tax(env, company_id, journal_sale, currency_id, revenue_account):
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine
    from dodoo.addons.account.models.account_tax import AccountTax

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
    tax_id = await AccountTax.create(
        env,
        {
            "name": "VAT 15.5%",
            "type_tax_use": "sale",
            "amount_type": "percent",
            "amount": Decimal("15.5"),
            "price_include": False,
            "company_id": company_id,
        },
    )
    await _add_tax_repartition_line(env, tax_id, company_id)
    # Each line's raw tax is 64.5484 * 15.5% = 10.005002 — rounds up to 10.01
    # individually, but the raw *sum* (20.010004) rounds down to 20.01.
    for _ in range(2):
        await AccountMoveLine.create(
            env,
            {
                "move_id": move_id,
                "account_id": revenue_account,
                "date": datetime.date.today(),
                "display_type": "product",
                "price_unit": Decimal("64.5484"),
                "quantity": 1,
                "credit": Decimal("64.5484"),
                "tax_ids": [tax_id],
            },
        )
    return move_id


@pytest.mark.asyncio
async def test_round_globally_default(env, company_id, journal_sale, currency_id, revenue_account):
    """FR-015: round_globally (the pre-existing default) sums raw per-line tax
    amounts first, then rounds once."""
    from dodoo.addons.account.models.account_move import AccountMove

    move_id = await _two_line_invoice_with_tax(
        env, company_id, journal_sale, currency_id, revenue_account
    )
    await AccountMove.action_post(env, [move_id])
    rows = await AccountMove.read(env, [move_id], ["amount_tax"])
    assert Decimal(str(rows[0]["amount_tax"])) == Decimal("20.01")


@pytest.mark.asyncio
async def test_round_per_line(env, company_id, journal_sale, currency_id, revenue_account):
    """FR-015: round_per_line rounds each line's own tax contribution before
    summing, producing a different (here, higher) total than round_globally."""
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.base.models.res_company import ResCompany

    await ResCompany.write(env, [company_id], {"tax_rounding_method": "round_per_line"})
    move_id = await _two_line_invoice_with_tax(
        env, company_id, journal_sale, currency_id, revenue_account
    )
    await AccountMove.action_post(env, [move_id])
    rows = await AccountMove.read(env, [move_id], ["amount_tax"])
    assert Decimal(str(rows[0]["amount_tax"])) == Decimal("20.02")

    # Restore default so this test doesn't leak state into others sharing the DB.
    await ResCompany.write(env, [company_id], {"tax_rounding_method": "round_globally"})
