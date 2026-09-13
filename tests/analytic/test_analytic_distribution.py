"""Model-level building blocks the `account`-side `analytic_distribution`
validation (FR-038, ADR-045) relies on — exercised here at the `analytic`
addon's own boundary since `tests/analytic/` installs only `analytic`
standalone; the full account.move.line write-guard integration test lives in
`tests/accounting/test_analytic_accounting.py` where both addons coexist.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_active_analytic_account_is_found_by_id(env, company_id):
    from dodoo.addons.analytic.models.analytic_account import AnalyticAccount

    account_id = await AnalyticAccount.create(
        env, {"name": "Active Account", "company_id": company_id}
    )
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT id FROM analytic_account WHERE id = ANY(:ids) AND active = TRUE"),
            {"ids": [account_id]},
        )
        found = {r[0] for r in row}
    assert found == {account_id}


@pytest.mark.asyncio
async def test_archived_analytic_account_is_excluded_by_active_filter(env, company_id):
    from dodoo.addons.analytic.models.analytic_account import AnalyticAccount

    account_id = await AnalyticAccount.create(
        env, {"name": "Archived Account", "company_id": company_id, "active": False}
    )
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT id FROM analytic_account WHERE id = ANY(:ids) AND active = TRUE"),
            {"ids": [account_id]},
        )
        found = {r[0] for r in row}
    assert found == set()  # the exact query the account-side write-guard uses


@pytest.mark.asyncio
async def test_unknown_analytic_account_id_never_matches(env, company_id):
    from dodoo.addons.analytic.models.analytic_account import AnalyticAccount

    account_id = await AnalyticAccount.create(
        env, {"name": "Some Account", "company_id": company_id}
    )
    unknown_id = account_id + 999999
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT id FROM analytic_account WHERE id = ANY(:ids) AND active = TRUE"),
            {"ids": [account_id, unknown_id]},
        )
        found = {r[0] for r in row}
    assert found == {account_id}
    assert unknown_id not in found


def test_percentage_sum_tolerance():
    """The ±0.01 tolerance FR-038 specifies for a distribution's percentages."""
    valid = {1: Decimal("60"), 2: Decimal("40")}
    total = sum(valid.values())
    assert abs(total - Decimal("100")) <= Decimal("0.01")

    invalid = {1: Decimal("60"), 2: Decimal("30")}
    total_invalid = sum(invalid.values())
    assert abs(total_invalid - Decimal("100")) > Decimal("0.01")

    borderline = {1: Decimal("60.005"), 2: Decimal("39.995")}
    assert abs(sum(borderline.values()) - Decimal("100")) <= Decimal("0.01")
