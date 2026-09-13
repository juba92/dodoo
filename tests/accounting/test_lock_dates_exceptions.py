"""Fiscal lock-date auto-advance-with-warning (including the exact boundary
case) and lock-exception grant/revoke/expiry scoping (FR-031/032/033,
ADR-039)."""
from __future__ import annotations

import datetime

import pytest
import pytest_asyncio
from sqlalchemy import text


@pytest_asyncio.fixture
async def admin_uid(env):
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT id FROM res_users WHERE login = 'admin' LIMIT 1")
        )
        return row.scalar_one()


async def _make_journal(env, company_id, code, jtype="sale"):
    from dodoo.addons.account.models.account_journal import AccountJournal

    return await AccountJournal.create(
        env, {"name": f"Journal {code}", "code": code, "type": jtype, "company_id": company_id}
    )


async def _make_invoice(env, company_id, currency_id, journal_id, revenue_account, date):
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine

    move_id = await AccountMove.create(
        env,
        {
            "move_type": "out_invoice",
            "journal_id": journal_id,
            "company_id": company_id,
            "currency_id": currency_id,
            "date": date,
        },
    )
    await AccountMoveLine.create(
        env,
        {
            "move_id": move_id,
            "account_id": revenue_account,
            "date": date,
            "display_type": "product",
            "price_unit": 100,
            "quantity": 1,
            "credit": 100,
        },
    )
    return move_id


@pytest_asyncio.fixture
async def clear_company_locks(env, company_id):
    """`company_id` is a shared, session-wide row — always clear every lock
    date this file might set, even on failure, so later tests are unaffected."""
    from dodoo.addons.base.models.res_company import ResCompany

    yield
    await ResCompany.write(
        env,
        [company_id],
        {
            "fiscalyear_lock_date": None,
            "tax_lock_date": None,
            "sale_lock_date": None,
            "purchase_lock_date": None,
        },
    )


@pytest.mark.asyncio
async def test_lock_date_boundary_advances_and_warns(
    env, company_id, currency_id, revenue_account, clear_company_locks
):
    """FR-032: a move dated exactly ON the lock date (not just before it) is
    also blocked and pushed forward, with a warning collected."""
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.base.models.res_company import ResCompany

    journal_id = await _make_journal(env, company_id, "LKB1")
    lock_date = datetime.date(2026, 3, 15)
    await ResCompany.write(env, [company_id], {"fiscalyear_lock_date": lock_date})

    move_id = await _make_invoice(
        env, company_id, currency_id, journal_id, revenue_account, lock_date
    )
    warnings: list[str] = []
    await AccountMove.action_post(env, [move_id], _warnings=warnings)

    assert len(warnings) == 1
    rows = await AccountMove.read(env, [move_id], ["date", "state"])
    assert rows[0]["state"] == "posted"
    assert rows[0]["date"] == lock_date + datetime.timedelta(days=1)


@pytest.mark.asyncio
async def test_lock_date_before_is_unaffected(
    env, company_id, currency_id, revenue_account, clear_company_locks
):
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.base.models.res_company import ResCompany

    journal_id = await _make_journal(env, company_id, "LKB2")
    lock_date = datetime.date(2026, 3, 15)
    await ResCompany.write(env, [company_id], {"fiscalyear_lock_date": lock_date})

    move_date = datetime.date(2026, 4, 1)
    move_id = await _make_invoice(
        env, company_id, currency_id, journal_id, revenue_account, move_date
    )
    warnings: list[str] = []
    await AccountMove.action_post(env, [move_id], _warnings=warnings)

    assert warnings == []
    rows = await AccountMove.read(env, [move_id], ["date"])
    assert rows[0]["date"] == move_date


@pytest.mark.asyncio
async def test_lock_exception_still_blocks_up_to_its_own_date(
    env, company_id, currency_id, revenue_account, admin_uid, clear_company_locks
):
    """FR-033: an exception replaces the company lock with its own (later,
    still-enforced) date — it does not fully unlock the journal."""
    from dodoo.addons.account.models.account_lock_exception import AccountLockException
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.base.models.res_company import ResCompany

    journal_id = await _make_journal(env, company_id, "LKX1")
    await ResCompany.write(
        env, [company_id], {"sale_lock_date": datetime.date(2026, 1, 5)}
    )
    await AccountLockException.create(
        env,
        {
            "company_id": company_id,
            "lock_date_field": "sale_lock_date",
            "lock_date": datetime.date(2026, 1, 25),
            "journal_id": journal_id,
            "end_date": datetime.date(2026, 12, 31),
            "granted_by_id": admin_uid,
        },
    )

    # Still before the exception's own (more permissive) date -> still blocked.
    move_id = await _make_invoice(
        env, company_id, currency_id, journal_id, revenue_account, datetime.date(2026, 1, 15)
    )
    warnings: list[str] = []
    await AccountMove.action_post(env, [move_id], _warnings=warnings)
    assert len(warnings) == 1
    rows = await AccountMove.read(env, [move_id], ["date"])
    assert rows[0]["date"] == datetime.date(2026, 1, 26)

    # After the exception's own date -> unaffected.
    move_id2 = await _make_invoice(
        env, company_id, currency_id, journal_id, revenue_account, datetime.date(2026, 1, 30)
    )
    warnings2: list[str] = []
    await AccountMove.action_post(env, [move_id2], _warnings=warnings2)
    assert warnings2 == []


@pytest.mark.asyncio
async def test_expired_lock_exception_does_not_apply(
    env, company_id, currency_id, revenue_account, admin_uid, clear_company_locks
):
    from dodoo.addons.account.models.account_lock_exception import AccountLockException
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.base.models.res_company import ResCompany

    journal_id = await _make_journal(env, company_id, "LKX2")
    await ResCompany.write(
        env, [company_id], {"sale_lock_date": datetime.date(2026, 1, 5)}
    )
    await AccountLockException.create(
        env,
        {
            "company_id": company_id,
            "lock_date_field": "sale_lock_date",
            "lock_date": datetime.date(2026, 1, 25),
            "journal_id": journal_id,
            "end_date": datetime.date(2025, 12, 31),  # already expired
            "granted_by_id": admin_uid,
        },
    )

    move_id = await _make_invoice(
        env, company_id, currency_id, journal_id, revenue_account, datetime.date(2026, 1, 3)
    )
    warnings: list[str] = []
    await AccountMove.action_post(env, [move_id], _warnings=warnings)
    # The expired exception is ignored — the company's own sale_lock_date applies.
    assert len(warnings) == 1
    rows = await AccountMove.read(env, [move_id], ["date"])
    assert rows[0]["date"] == datetime.date(2026, 1, 6)


@pytest.mark.asyncio
async def test_revoked_lock_exception_no_longer_applies(
    env, company_id, currency_id, revenue_account, admin_uid, clear_company_locks
):
    from dodoo.addons.account.models.account_lock_exception import AccountLockException
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.base.models.res_company import ResCompany

    journal_id = await _make_journal(env, company_id, "LKX3")
    await ResCompany.write(
        env, [company_id], {"sale_lock_date": datetime.date(2026, 1, 5)}
    )
    exception_id = await AccountLockException.create(
        env,
        {
            "company_id": company_id,
            "lock_date_field": "sale_lock_date",
            "lock_date": datetime.date(2026, 1, 25),
            "journal_id": journal_id,
            "end_date": datetime.date(2026, 12, 31),
            "granted_by_id": admin_uid,
        },
    )
    await AccountLockException.write(env, [exception_id], {"active": False})

    move_id = await _make_invoice(
        env, company_id, currency_id, journal_id, revenue_account, datetime.date(2026, 1, 3)
    )
    warnings: list[str] = []
    await AccountMove.action_post(env, [move_id], _warnings=warnings)
    # The revoked exception no longer masks the company's own lock date.
    assert len(warnings) == 1
    rows = await AccountMove.read(env, [move_id], ["date"])
    assert rows[0]["date"] == datetime.date(2026, 1, 6)


@pytest.mark.asyncio
async def test_lock_exception_grant_requires_manager(env, company_id):
    """SEC-002: a user with no "Accounting Manager" group is rejected by the
    same `require_groups` check the lock-exception-grant/hash-chain-toggle
    routes use (A01 — non-manager granting a lock exception)."""
    from dodoo.addons.account.security import GROUP_MANAGER
    from dodoo.addons.account.validators import require_groups
    from dodoo.addons.base.models.res_users import ResUsers
    from dodoo.core.exceptions import AccessError

    plain_uid = await ResUsers.create(
        env, {"login": "plain_user_no_groups", "name": "Plain User"}
    )
    with pytest.raises(AccessError):
        await require_groups(env, plain_uid, GROUP_MANAGER)
