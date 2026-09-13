"""Per-journal sequence scoping, concurrent posting, draft-only cancel,
reused-number-on-repost, and draft-reversal option (FR-003/004/005/006,
ADR-038)."""
from __future__ import annotations

import asyncio
import datetime

import pytest

from dodoo.core.exceptions import DodooError


async def _make_journal(env, company_id, code, jtype="sale"):
    from dodoo.addons.account.models.account_journal import AccountJournal

    return await AccountJournal.create(
        env,
        {"name": f"Journal {code}", "code": code, "type": jtype, "company_id": company_id},
    )


async def _make_invoice(env, company_id, currency_id, journal_id, revenue_account):
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine

    move_id = await AccountMove.create(
        env,
        {
            "move_type": "out_invoice",
            "journal_id": journal_id,
            "company_id": company_id,
            "currency_id": currency_id,
            "date": datetime.date(2026, 1, 15),
        },
    )
    await AccountMoveLine.create(
        env,
        {
            "move_id": move_id,
            "account_id": revenue_account,
            "date": datetime.date(2026, 1, 15),
            "display_type": "product",
            "price_unit": 100,
            "quantity": 1,
            "credit": 100,
        },
    )
    return move_id


@pytest.mark.asyncio
async def test_per_journal_sequence_scoping(env, company_id, currency_id, revenue_account):
    from dodoo.addons.account.models.account_move import AccountMove

    journal_a = await _make_journal(env, company_id, "SJA")
    journal_b = await _make_journal(env, company_id, "SJB")

    move_a1 = await _make_invoice(env, company_id, currency_id, journal_a, revenue_account)
    await AccountMove.action_post(env, [move_a1])
    move_b1 = await _make_invoice(env, company_id, currency_id, journal_b, revenue_account)
    await AccountMove.action_post(env, [move_b1])
    move_a2 = await _make_invoice(env, company_id, currency_id, journal_a, revenue_account)
    await AccountMove.action_post(env, [move_a2])

    rows = await AccountMove.read(env, [move_a1, move_b1, move_a2], ["name"])
    names = {r["id"]: r["name"] for r in rows}

    assert names[move_a1] == "SJA/2026/0001"
    assert names[move_b1] == "SJB/2026/0001"
    # Journal A's second post continues its own counter, unaffected by journal B.
    assert names[move_a2] == "SJA/2026/0002"


@pytest.mark.asyncio
async def test_concurrent_posting_no_duplicate_or_skipped_sequence(
    env, company_id, currency_id, revenue_account
):
    from dodoo.addons.account.models.account_move import AccountMove

    journal_id = await _make_journal(env, company_id, "CONC")
    move_ids = [
        await _make_invoice(env, company_id, currency_id, journal_id, revenue_account)
        for _ in range(5)
    ]

    await asyncio.gather(*(AccountMove.action_post(env, [mid]) for mid in move_ids))

    rows = await AccountMove.read(env, move_ids, ["name"])
    names = sorted(r["name"] for r in rows)
    assert names == [f"CONC/2026/{n:04d}" for n in range(1, 6)]


@pytest.mark.asyncio
async def test_action_cancel_draft_only(env, company_id, currency_id, revenue_account):
    from dodoo.addons.account.models.account_move import AccountMove

    journal_id = await _make_journal(env, company_id, "CANC")
    draft_move = await _make_invoice(env, company_id, currency_id, journal_id, revenue_account)

    await AccountMove.action_cancel(env, [draft_move])
    rows = await AccountMove.read(env, [draft_move], ["state"])
    assert rows[0]["state"] == "cancel"

    # A cancelled move cannot be posted.
    with pytest.raises(DodooError):
        await AccountMove.action_post(env, [draft_move])

    # A posted move cannot be cancelled directly (must be reversed).
    posted_move = await _make_invoice(env, company_id, currency_id, journal_id, revenue_account)
    await AccountMove.action_post(env, [posted_move])
    with pytest.raises(DodooError):
        await AccountMove.action_cancel(env, [posted_move])


@pytest.mark.asyncio
async def test_reused_number_on_repost(env, company_id, currency_id, revenue_account):
    from dodoo.addons.account.models.account_move import AccountMove

    journal_id = await _make_journal(env, company_id, "REPO")
    move_id = await _make_invoice(env, company_id, currency_id, journal_id, revenue_account)

    await AccountMove.action_post(env, [move_id])
    rows = await AccountMove.read(env, [move_id], ["name"])
    original_name = rows[0]["name"]
    assert original_name == "REPO/2026/0001"

    await AccountMove.action_reset_to_draft(env, [move_id])
    await AccountMove.action_post(env, [move_id])

    rows = await AccountMove.read(env, [move_id], ["name"])
    assert rows[0]["name"] == original_name

    # The next brand-new move still gets the next fresh number, not a
    # duplicate of the reused one.
    move_id2 = await _make_invoice(env, company_id, currency_id, journal_id, revenue_account)
    await AccountMove.action_post(env, [move_id2])
    rows2 = await AccountMove.read(env, [move_id2], ["name"])
    assert rows2[0]["name"] == "REPO/2026/0002"


@pytest.mark.asyncio
async def test_action_reverse_auto_post_false_leaves_draft(
    env, company_id, currency_id, revenue_account
):
    from dodoo.addons.account.models.account_move import AccountMove

    journal_id = await _make_journal(env, company_id, "REVD")
    move_id = await _make_invoice(env, company_id, currency_id, journal_id, revenue_account)
    await AccountMove.action_post(env, [move_id])

    reversal_ids = await AccountMove.action_reverse(env, [move_id], auto_post=False)
    rows = await AccountMove.read(env, reversal_ids, ["state", "reversed_entry_id"])
    assert rows[0]["state"] == "draft"
    assert rows[0]["reversed_entry_id"] == move_id

    # The caller can still post it manually.
    await AccountMove.action_post(env, reversal_ids)
    rows2 = await AccountMove.read(env, reversal_ids, ["state"])
    assert rows2[0]["state"] == "posted"
