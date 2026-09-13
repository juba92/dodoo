"""Payment-term 100%-sum validation, days_end_of_month_on_the/next_month fix, and
early-payment-discount activation (FR-017/018/019, ADR-041)."""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from dodoo.core.exceptions import DodooError


@pytest.mark.asyncio
async def test_percent_lines_accept_exact_100(env, company_id):
    from dodoo.addons.account.models.account_payment_term import (
        AccountPaymentTerm,
        AccountPaymentTermLine,
    )

    term_id = await AccountPaymentTerm.create(
        env, {"name": "40/30/30", "company_id": company_id}
    )
    for pct in (40, 30, 30):
        await AccountPaymentTermLine.create(
            env,
            {
                "payment_term_id": term_id,
                "value": "percent",
                "value_amount": pct,
                "delay_type": "days_after",
                "nb_days": 30,
            },
        )
    # No exception raised; the term is usable.
    installments = await AccountPaymentTerm.compute_installments(
        env, term_id, datetime.date(2026, 1, 1), Decimal("100")
    )
    assert len(installments) == 3
    assert sum((i["amount"] for i in installments), Decimal("0")) == Decimal("100")


@pytest.mark.asyncio
async def test_percent_lines_reject_over_100(env, company_id):
    from dodoo.addons.account.models.account_payment_term import (
        AccountPaymentTerm,
        AccountPaymentTermLine,
    )

    term_id = await AccountPaymentTerm.create(
        env, {"name": "Over 100", "company_id": company_id}
    )
    await AccountPaymentTermLine.create(
        env,
        {
            "payment_term_id": term_id,
            "value": "percent",
            "value_amount": 60,
            "delay_type": "days_after",
            "nb_days": 30,
        },
    )
    with pytest.raises(DodooError):
        await AccountPaymentTermLine.create(
            env,
            {
                "payment_term_id": term_id,
                "value": "percent",
                "value_amount": 50,  # 60 + 50 = 110% — exceeds 100
                "delay_type": "days_after",
                "nb_days": 30,
            },
        )


@pytest.mark.asyncio
async def test_incomplete_term_rejected_at_use_time(env, company_id):
    """A term whose percent lines sum to less than 100% never hard-errors at
    write time (still under construction) but must be rejected when actually
    used to compute installments (FR-017)."""
    from dodoo.addons.account.models.account_payment_term import (
        AccountPaymentTerm,
        AccountPaymentTermLine,
    )

    term_id = await AccountPaymentTerm.create(
        env, {"name": "Incomplete", "company_id": company_id}
    )
    await AccountPaymentTermLine.create(
        env,
        {
            "payment_term_id": term_id,
            "value": "percent",
            "value_amount": 60,
            "delay_type": "days_after",
            "nb_days": 30,
        },
    )
    with pytest.raises(DodooError):
        await AccountPaymentTerm.compute_installments(
            env, term_id, datetime.date(2026, 1, 1), Decimal("100")
        )


@pytest.mark.asyncio
async def test_days_end_of_month_on_the_next_month(env, company_id):
    """FR-019: with next_month=True, the due date lands on the configured day of
    the *following* month, not the invoice month's literal end."""
    from dodoo.addons.account.models.account_payment_term import (
        AccountPaymentTerm,
        AccountPaymentTermLine,
    )

    term_id = await AccountPaymentTerm.create(
        env, {"name": "EOM 15th next month", "company_id": company_id}
    )
    await AccountPaymentTermLine.create(
        env,
        {
            "payment_term_id": term_id,
            "value": "percent",
            "value_amount": 100,
            "delay_type": "days_end_of_month_on_the",
            "nb_days": 15,
            "next_month": True,
        },
    )
    installments = await AccountPaymentTerm.compute_installments(
        env, term_id, datetime.date(2026, 3, 10), Decimal("100")
    )
    assert installments[0]["due_date"] == datetime.date(2026, 4, 15)


@pytest.mark.asyncio
async def test_days_end_of_month_on_the_same_month_unchanged(env, company_id):
    """next_month defaults to False — existing terms keep today's exact output."""
    from dodoo.addons.account.models.account_payment_term import (
        AccountPaymentTerm,
        AccountPaymentTermLine,
    )

    term_id = await AccountPaymentTerm.create(
        env, {"name": "EOM 15th same month", "company_id": company_id}
    )
    await AccountPaymentTermLine.create(
        env,
        {
            "payment_term_id": term_id,
            "value": "percent",
            "value_amount": 100,
            "delay_type": "days_end_of_month_on_the",
            "nb_days": 15,
        },
    )
    installments = await AccountPaymentTerm.compute_installments(
        env, term_id, datetime.date(2026, 3, 10), Decimal("100")
    )
    assert installments[0]["due_date"] == datetime.date(2026, 3, 15)


@pytest.mark.asyncio
async def test_early_payment_discount_keys_present(env, company_id, revenue_account):
    """FR-018: an early_discount=True term exposes discount_date/discount_amount
    per installment."""
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
            "early_payment_discount_account_id": revenue_account,
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
    installments = await AccountPaymentTerm.compute_installments(
        env, term_id, datetime.date(2026, 1, 1), Decimal("100")
    )
    inst = installments[0]
    assert inst["discount_date"] == datetime.date(2026, 1, 11)
    assert inst["discount_amount"] == Decimal("98.00")


@pytest.mark.asyncio
async def test_no_early_discount_keys_when_disabled(env, company_id):
    from dodoo.addons.account.models.account_payment_term import (
        AccountPaymentTerm,
        AccountPaymentTermLine,
    )

    term_id = await AccountPaymentTerm.create(
        env, {"name": "Net 30", "company_id": company_id}
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
    installments = await AccountPaymentTerm.compute_installments(
        env, term_id, datetime.date(2026, 1, 1), Decimal("100")
    )
    assert "discount_date" not in installments[0]
