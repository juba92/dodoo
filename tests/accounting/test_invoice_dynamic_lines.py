"""Dynamic invoice-line fields: quantity, price_unit, tax_ids (Many2many) and the
draft-total recompute that backs the live client-side preview."""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text


@pytest_asyncio.fixture
async def sale_tax_14(env, company_id):
    """A plain 14% sale tax (no repartition lines — not needed for totals)."""
    from dodoo.addons.account.models.account_tax import AccountTax

    return await AccountTax.create(
        env,
        {
            "name": "VAT 14%",
            "type_tax_use": "sale",
            "amount_type": "percent",
            "amount": 14,
            "company_id": company_id,
        },
    )


@pytest_asyncio.fixture
async def sale_tax_5(env, company_id):
    from dodoo.addons.account.models.account_tax import AccountTax

    return await AccountTax.create(
        env,
        {
            "name": "Svc 5%",
            "type_tax_use": "sale",
            "amount_type": "percent",
            "amount": 5,
            "company_id": company_id,
        },
    )


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
async def test_price_subtotal_derived_from_unit_and_qty(
    env, draft_invoice, revenue_account
):
    from dodoo.addons.account.models.account_move_line import AccountMoveLine

    line_id = await AccountMoveLine.create(
        env,
        {
            "move_id": draft_invoice,
            "account_id": revenue_account,
            "date": datetime.date.today(),
            "display_type": "product",
            "price_unit": 30,
            "quantity": 4,
            "credit": 120,
        },
    )
    rows = await AccountMoveLine.read(
        env, [line_id], ["price_unit", "quantity", "price_subtotal"]
    )
    assert Decimal(str(rows[0]["price_subtotal"])) == Decimal("120")


@pytest.mark.asyncio
async def test_tax_ids_many2many_write_and_read(
    env, draft_invoice, revenue_account, sale_tax_14, sale_tax_5
):
    from dodoo.addons.account.models.account_move_line import AccountMoveLine

    line_id = await AccountMoveLine.create(
        env,
        {
            "move_id": draft_invoice,
            "account_id": revenue_account,
            "date": datetime.date.today(),
            "display_type": "product",
            "price_unit": 100,
            "quantity": 1,
            "credit": 100,
            "tax_ids": [sale_tax_14, sale_tax_5],
        },
    )

    rows = await AccountMoveLine.read(env, [line_id], ["tax_ids"])
    assert sorted(rows[0]["tax_ids"]) == sorted([sale_tax_14, sale_tax_5])

    # Junction rows actually exist
    async with env.dml_conn() as conn:
        cnt = await conn.execute(
            text(
                "SELECT COUNT(*) FROM account_move_line_tax_rel WHERE move_line_id = :lid"
            ),
            {"lid": line_id},
        )
        assert cnt.scalar_one() == 2

    # Rewrite replaces the set
    await AccountMoveLine.write(env, [line_id], {"tax_ids": [sale_tax_14]})
    rows = await AccountMoveLine.read(env, [line_id], ["tax_ids"])
    assert rows[0]["tax_ids"] == [sale_tax_14]


@pytest.mark.asyncio
async def test_m2m_absent_from_default_read(
    env, draft_invoice, revenue_account, sale_tax_14
):
    from dodoo.addons.account.models.account_move_line import AccountMoveLine

    line_id = await AccountMoveLine.create(
        env,
        {
            "move_id": draft_invoice,
            "account_id": revenue_account,
            "date": datetime.date.today(),
            "display_type": "product",
            "price_unit": 10,
            "quantity": 1,
            "credit": 10,
            "tax_ids": [sale_tax_14],
        },
    )
    # A read that does not ask for tax_ids must not return it
    rows = await AccountMoveLine.read(env, [line_id], ["name", "price_unit"])
    assert "tax_ids" not in rows[0]
    assert "id" in rows[0]


@pytest.mark.asyncio
async def test_recompute_totals_draft_invoice(
    env, draft_invoice, revenue_account, sale_tax_14
):
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine

    today = datetime.date.today()
    # 2 lines: 120.00 and 50.00 untaxed, both carrying VAT 14%
    for unit, qty, credit in [(60, 2, 120), (50, 1, 50)]:
        await AccountMoveLine.create(
            env,
            {
                "move_id": draft_invoice,
                "account_id": revenue_account,
                "date": today,
                "display_type": "product",
                "price_unit": unit,
                "quantity": qty,
                "credit": credit,
                "tax_ids": [sale_tax_14],
            },
        )

    totals = await AccountMove.recompute_totals(env, [draft_invoice])
    assert totals[draft_invoice]["amount_untaxed"] == "170.00"
    # 170 * 14% = 23.80 (round-globally, one tax)
    assert totals[draft_invoice]["amount_tax"] == "23.80"
    assert totals[draft_invoice]["amount_total"] == "193.80"

    rows = await AccountMove.read(
        env, [draft_invoice], ["amount_untaxed", "amount_tax", "amount_total"]
    )
    assert Decimal(str(rows[0]["amount_total"])) == Decimal("193.80")


@pytest.mark.asyncio
async def test_recompute_totals_skips_posted(
    env, company_id, currency_id, journal_sale, ar_account, revenue_account
):
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
                    "(move_id, account_id, date, display_type, debit, credit, balance, "
                    "create_date, write_date) "
                    "VALUES (:mid, :acct, :dt, 'product', :d, :c, :b, now(), now())"
                ),
                {"mid": move_id, "acct": acct, "dt": today, "d": debit, "c": credit,
                 "b": debit - credit},
            )
        await conn.commit()
    await AccountMove.action_post(env, [move_id])
    before = await AccountMove.read(env, [move_id], ["amount_total"])

    result = await AccountMove.recompute_totals(env, [move_id])
    assert move_id not in result  # posted move left untouched

    after = await AccountMove.read(env, [move_id], ["amount_total"])
    assert after[0]["amount_total"] == before[0]["amount_total"]
