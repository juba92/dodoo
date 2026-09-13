"""End-to-end: registering a payment within an early-payment-discount window
actually reduces what the customer owes and fully closes the invoice
(FR-018, ADR-041/T029)."""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text


@pytest_asyncio.fixture
async def bank_journal(env, company_id):
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT id FROM account_journal WHERE type='bank' AND company_id=:cid LIMIT 1"),
            {"cid": company_id},
        )
        return row.scalar_one()


@pytest_asyncio.fixture
async def discount_income_account(env, company_id):
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT id FROM account_account WHERE code='4100' AND company_id=:cid LIMIT 1"
            ),
            {"cid": company_id},
        )
        return row.scalar_one()


@pytest.mark.asyncio
async def test_payment_within_discount_window_closes_invoice_at_discounted_amount(
    env,
    company_id,
    currency_id,
    journal_sale,
    bank_journal,
    revenue_account,
    ar_account,
    partner_id,
    discount_income_account,
):
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine
    from dodoo.addons.account.models.account_payment import AccountPayment
    from dodoo.addons.account.models.account_payment_term import (
        AccountPaymentTerm,
        AccountPaymentTermLine,
    )

    term_id = await AccountPaymentTerm.create(
        env,
        {
            "name": "2/10 Net 30",
            "company_id": company_id,
            "early_discount": True,
            "discount_percentage": 2,
            "discount_days": 10,
            "early_payment_discount_account_id": discount_income_account,
        },
    )
    await AccountPaymentTermLine.create(
        env,
        {
            "payment_term_id": term_id,
            "value": "percent",
            "value_amount": 100,
            "delay_type": "days_after",
            "nb_days": 30,
        },
    )

    invoice_date = datetime.date(2026, 1, 1)
    move_id = await AccountMove.create(
        env,
        {
            "move_type": "out_invoice",
            "journal_id": journal_sale,
            "company_id": company_id,
            "currency_id": currency_id,
            "partner_id": partner_id,
            "date": invoice_date,
            "invoice_date": invoice_date,
            "invoice_payment_term_id": term_id,
        },
    )
    await AccountMoveLine.create(
        env,
        {
            "move_id": move_id,
            "account_id": revenue_account,
            "date": invoice_date,
            "display_type": "product",
            "price_unit": 100,
            "quantity": 1,
            "credit": 100,
        },
    )
    await AccountMove.action_post(env, [move_id])

    payment_id = await AccountPayment.create(
        env,
        {
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": partner_id,
            "journal_id": bank_journal,
            "currency_id": currency_id,
            "amount": Decimal("98"),  # pays the 2%-discounted amount, not the full 100
            "date": datetime.date(2026, 1, 5),  # within the 10-day discount window
            "company_id": company_id,
        },
    )
    await AccountPayment.action_post(env, [payment_id])
    result = await AccountPayment.register_against_invoices(env, payment_id, [move_id])

    assert len(result["reconciled"]) == 1

    rows = await AccountMove.read(env, [move_id], ["payment_state", "amount_residual"])
    assert rows[0]["payment_state"] == "paid"
    assert Decimal(str(rows[0]["amount_residual"])) == Decimal("0.00")
