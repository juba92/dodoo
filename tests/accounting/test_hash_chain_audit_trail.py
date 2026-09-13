"""Hash-chain compute/verify, posted-line write rejection, and
action_reset_to_draft rejection for hash-secured/lock-dated moves
(FR-007/008/009, ADR-039)."""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy import text

from dodoo.core.exceptions import DodooError


async def _make_hash_journal(env, company_id, code="HCJ"):
    from dodoo.addons.account.models.account_journal import AccountJournal

    return await AccountJournal.create(
        env,
        {
            "name": f"Hash Journal {code}",
            "code": code,
            "type": "sale",
            "company_id": company_id,
            "restrict_mode_hash_table": True,
        },
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


@pytest.mark.asyncio
async def test_hash_chain_computed_and_verified(env, company_id, currency_id, revenue_account):
    from dodoo.addons.account.models.account_move import AccountMove

    journal_id = await _make_hash_journal(env, company_id, "HCJ1")
    move1 = await _make_invoice(
        env, company_id, currency_id, journal_id, revenue_account, datetime.date(2026, 1, 10)
    )
    move2 = await _make_invoice(
        env, company_id, currency_id, journal_id, revenue_account, datetime.date(2026, 1, 11)
    )
    await AccountMove.action_post(env, [move1])
    await AccountMove.action_post(env, [move2])

    rows = await AccountMove.read(
        env, [move1, move2], ["inalterable_hash", "secure_sequence_number"]
    )
    by_id = {r["id"]: r for r in rows}
    assert by_id[move1]["inalterable_hash"] is not None
    assert by_id[move2]["inalterable_hash"] is not None
    assert by_id[move2]["secure_sequence_number"] > by_id[move1]["secure_sequence_number"]

    result = await AccountMove.verify_hash_chain(env, journal_id)
    assert result == {"valid": True, "first_break_move_id": None}


@pytest.mark.asyncio
async def test_hash_chain_detects_tampering(env, company_id, currency_id, revenue_account):
    from dodoo.addons.account.models.account_move import AccountMove

    journal_id = await _make_hash_journal(env, company_id, "HCJ2")
    move1 = await _make_invoice(
        env, company_id, currency_id, journal_id, revenue_account, datetime.date(2026, 1, 10)
    )
    await AccountMove.action_post(env, [move1])

    # Simulate direct DB tampering (bypassing the app's own immutability
    # guard) — the stored amount_total no longer matches what was hashed.
    async with env.dml_conn() as conn:
        await conn.execute(
            text("UPDATE account_move SET amount_total = amount_total + 1 WHERE id=:id"),
            {"id": move1},
        )
        await conn.commit()

    result = await AccountMove.verify_hash_chain(env, journal_id)
    assert result["valid"] is False
    assert result["first_break_move_id"] == move1


@pytest.mark.asyncio
async def test_posted_line_write_rejected(env, company_id, currency_id, revenue_account):
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine

    journal_id = await _make_hash_journal(env, company_id, "HCJ3")
    move_id = await _make_invoice(
        env, company_id, currency_id, journal_id, revenue_account, datetime.date(2026, 1, 10)
    )
    await AccountMove.action_post(env, [move_id])

    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT id FROM account_move_line WHERE move_id=:mid LIMIT 1"),
            {"mid": move_id},
        )
        line_id = row.scalar_one()

    with pytest.raises(DodooError):
        await AccountMoveLine.write(env, [line_id], {"name": "tampered"})


@pytest.mark.asyncio
async def test_reset_to_draft_rejected_for_hash_secured_move(
    env, company_id, currency_id, revenue_account
):
    from dodoo.addons.account.models.account_move import AccountMove

    journal_id = await _make_hash_journal(env, company_id, "HCJ4")
    move_id = await _make_invoice(
        env, company_id, currency_id, journal_id, revenue_account, datetime.date(2026, 1, 10)
    )
    await AccountMove.action_post(env, [move_id])

    with pytest.raises(DodooError):
        await AccountMove.action_reset_to_draft(env, [move_id])


@pytest.mark.asyncio
async def test_reset_to_draft_rejected_for_lock_dated_move(
    env, company_id, currency_id, revenue_account
):
    # A plain (non-hash) journal so only the lock-date rejection is exercised.
    from dodoo.addons.account.models.account_journal import AccountJournal
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.base.models.res_company import ResCompany

    journal_id = await AccountJournal.create(
        env,
        {"name": "Lock Journal", "code": "LKJ1", "type": "sale", "company_id": company_id},
    )
    move_id = await _make_invoice(
        env, company_id, currency_id, journal_id, revenue_account, datetime.date(2026, 1, 10)
    )
    await AccountMove.action_post(env, [move_id])

    # `company_id` is a shared, session-wide row — always clear the lock date
    # again so later tests in this file/session aren't silently affected.
    await ResCompany.write(
        env, [company_id], {"fiscalyear_lock_date": datetime.date(2026, 1, 20)}
    )
    try:
        with pytest.raises(DodooError):
            await AccountMove.action_reset_to_draft(env, [move_id])
    finally:
        await ResCompany.write(env, [company_id], {"fiscalyear_lock_date": None})
