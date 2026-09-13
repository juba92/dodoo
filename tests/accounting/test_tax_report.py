"""Tax Report aggregation by grid tag across posted invoices/bills (FR-016,
ADR-040/044).

Per [[accounting-test-isolation]]: run standalone, not batched with other
tests/accounting/ files — like test_reports_opening_balance.py, this
aggregates tagged tax amounts across the whole shared DB with no
company_id-scoped exclusivity guarantee for the tag itself.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest


@pytest.mark.asyncio
async def test_tax_report_aggregates_by_tag(env, company_id, currency_id, journal_sale, revenue_account):
    from dodoo.addons.account.models.account_account_tag import AccountAccountTag
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine
    from dodoo.addons.account.models.account_report import AccountReportTax
    from dodoo.addons.account.models.account_tax import (
        AccountTax,
        AccountTaxRepartitionLine,
    )

    async with env.dml_conn() as conn:
        from sqlalchemy import text

        vat_row = await conn.execute(
            text("SELECT id FROM account_account WHERE code='2500' AND company_id=:cid"),
            {"cid": company_id},
        )
        vat_account_id = vat_row.scalar_one()

    base_tag_id = await AccountAccountTag.create(env, {"name": "+GridBase", "applicability": "taxes"})
    tax_tag_id = await AccountAccountTag.create(env, {"name": "+GridTax", "applicability": "taxes"})

    tax_id = await AccountTax.create(
        env,
        {
            "name": "Tax Report VAT 10%",
            "type_tax_use": "sale",
            "amount_type": "percent",
            "amount": 10,
            "price_include": False,
            "company_id": company_id,
        },
    )
    base_rep_id = await AccountTaxRepartitionLine.create(
        env,
        {
            "tax_id": tax_id,
            "document_type": "invoice",
            "repartition_type": "base",
            "factor_percent": 100,
            "sequence": 1,
        },
    )
    tax_rep_id = await AccountTaxRepartitionLine.create(
        env,
        {
            "tax_id": tax_id,
            "document_type": "invoice",
            "repartition_type": "tax",
            "factor_percent": 100,
            "account_id": vat_account_id,
            "sequence": 2,
        },
    )
    await AccountTaxRepartitionLine.write(env, [base_rep_id], {"tag_ids": [base_tag_id]})
    await AccountTaxRepartitionLine.write(env, [tax_rep_id], {"tag_ids": [tax_tag_id]})

    move_id = await AccountMove.create(
        env,
        {
            "move_type": "out_invoice",
            "journal_id": journal_sale,
            "company_id": company_id,
            "currency_id": currency_id,
            "date": datetime.date(2024, 5, 1),
        },
    )
    await AccountMoveLine.create(
        env,
        {
            "move_id": move_id,
            "account_id": revenue_account,
            "date": datetime.date(2024, 5, 1),
            "display_type": "product",
            "price_unit": 200,
            "quantity": 1,
            "credit": 200,
            "tax_ids": [tax_id],
        },
    )
    await AccountMove.action_post(env, [move_id])

    rep = await AccountReportTax.get_report(
        env, date_from=datetime.date(2024, 1, 1), date_to=datetime.date(2024, 12, 31),
        company_id=company_id,
    )
    lines_by_tag = {r["tag_name"]: r for r in rep["lines"]}
    assert Decimal(lines_by_tag["+GridBase"]["base_amount"]) == Decimal("200.00")
    assert Decimal(lines_by_tag["+GridTax"]["tax_amount"]) == Decimal("20.00")
