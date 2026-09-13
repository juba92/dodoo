"""Aged-report 5-bucket boundary: a not-yet-due balance (days <= 0) routes to
"current", separate from the first overdue bucket (FR-036, ADR-044)."""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy import text

from dodoo.addons.account.models.account_report import _BUCKETS, _bucket_for


def test_bucket_for_boundaries():
    assert _bucket_for(0) == "current"
    assert _bucket_for(-5) == "current"
    assert _bucket_for(1) == "b_0_30"
    assert _bucket_for(30) == "b_0_30"
    assert _bucket_for(31) == "b_31_60"
    assert _bucket_for(60) == "b_31_60"
    assert _bucket_for(61) == "b_61_90"
    assert _bucket_for(90) == "b_61_90"
    assert _bucket_for(91) == "b_90_plus"


def test_buckets_tuple_has_five_entries_current_first():
    assert _BUCKETS == ("current", "b_0_30", "b_31_60", "b_61_90", "b_90_plus")


@pytest.mark.asyncio
async def test_not_yet_due_invoice_lands_in_current_not_overdue(
    env, company_id, currency_id, journal_sale, revenue_account
):
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_report import AccountReportAgedReceivable
    from dodoo.addons.base.models.res_partner import ResPartner

    # A dedicated partner (not the shared `partner_id` fixture) so this
    # test's bucket totals can't be polluted by unrelated tests' unreconciled
    # invoices against the same shared partner in this batched run.
    partner_id = await ResPartner.create(
        env, {"name": "Aged Bucket Test Partner", "is_company": True, "company_id": company_id}
    )

    today = datetime.date.today()
    due_in_ten_days = today + datetime.timedelta(days=10)
    move_id = await AccountMove.create(
        env,
        {
            "move_type": "out_invoice",
            "journal_id": journal_sale,
            "company_id": company_id,
            "currency_id": currency_id,
            "partner_id": partner_id,
            "date": today,
            "invoice_date": today,
            "invoice_date_due": due_in_ten_days,
        },
    )
    async with env.dml_conn() as conn:
        await conn.execute(
            text(
                "INSERT INTO account_move_line "
                "(move_id, account_id, partner_id, date, display_type, debit, credit, "
                "balance, create_date, write_date) "
                "VALUES (:mid, :a, :p, :dt, 'product', 0, 500, -500, now(), now())"
            ),
            {"mid": move_id, "a": revenue_account, "p": partner_id, "dt": today},
        )
        await conn.commit()
    await AccountMove.action_post(env, [move_id])

    rep = await AccountReportAgedReceivable.get_report(env, date=today, company_id=company_id)
    partner = next(p for p in rep["partners"] if p["partner_name"] == "Aged Bucket Test Partner")
    assert float(partner["current"]) == 500.0
    assert float(partner["b_0_30"]) == 0.0
    assert float(rep["totals"]["current"]) >= 500.0
