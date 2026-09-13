"""Chart-of-accounts group auto-classification and reconcile-type constraints
(FR-001/002, ADR-037)."""
from __future__ import annotations

import pytest

from dodoo.core.exceptions import DodooError


@pytest.mark.asyncio
async def test_group_id_resolved_from_code_prefix(env, company_id):
    from dodoo.addons.account.models.account_account import (
        AccountAccount,
        AccountAccountGroup,
    )

    account_id = await AccountAccount.create(
        env,
        {
            "code": "1400",
            "name": "Test Asset Account",
            "account_type": "asset_current",
            "company_id": company_id,
        },
    )
    rows = await AccountAccount.read(env, [account_id], ["group_id"])
    group_id = rows[0]["group_id"]
    assert group_id is not None

    group_rows = await AccountAccountGroup.read(
        env, [group_id], ["name", "code_prefix_start", "code_prefix_end"]
    )
    assert group_rows[0]["name"] == "Assets"


@pytest.mark.asyncio
async def test_group_id_reresolved_when_code_changes(env, company_id):
    from dodoo.addons.account.models.account_account import AccountAccount

    account_id = await AccountAccount.create(
        env,
        {
            "code": "1450",
            "name": "Test Asset Account 2",
            "account_type": "asset_current",
            "company_id": company_id,
        },
    )
    await AccountAccount.write(env, [account_id], {"code": "5150"})
    rows = await AccountAccount.read(env, [account_id], ["group_id"])
    group_id = rows[0]["group_id"]

    from dodoo.addons.account.models.account_account import AccountAccountGroup

    group_rows = await AccountAccountGroup.read(env, [group_id], ["name"])
    assert group_rows[0]["name"] == "Expenses"


@pytest.mark.asyncio
async def test_group_id_input_is_ignored(env, company_id):
    """FR-001: group_id is never accepted as client input, even if sent."""
    from dodoo.addons.account.models.account_account import AccountAccount

    account_id = await AccountAccount.create(
        env,
        {
            "code": "1460",
            "name": "Test Asset Account 3",
            "account_type": "asset_current",
            "company_id": company_id,
            "group_id": 999999,
        },
    )
    rows = await AccountAccount.read(env, [account_id], ["group_id"])
    assert rows[0]["group_id"] != 999999


@pytest.mark.asyncio
async def test_off_balance_cannot_be_reconcilable(env, company_id):
    from dodoo.addons.account.models.account_account import AccountAccount

    with pytest.raises(DodooError):
        await AccountAccount.create(
            env,
            {
                "code": "9100",
                "name": "Bad Off-Balance",
                "account_type": "off_balance",
                "company_id": company_id,
                "reconcile": True,
            },
        )


@pytest.mark.asyncio
async def test_cash_and_credit_card_force_reconcile_false(env, company_id):
    from dodoo.addons.account.models.account_account import AccountAccount

    cash_id = await AccountAccount.create(
        env,
        {
            "code": "1030",
            "name": "Petty Cash",
            "account_type": "asset_cash",
            "company_id": company_id,
        },
    )
    rows = await AccountAccount.read(env, [cash_id], ["reconcile"])
    assert rows[0]["reconcile"] is False

    with pytest.raises(DodooError):
        await AccountAccount.write(env, [cash_id], {"reconcile": True})
