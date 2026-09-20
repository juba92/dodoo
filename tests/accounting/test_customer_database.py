"""Customer database: CRUD/archive/delete-guard (US1), search (US2), and the
on-demand AR ledger (US3). FR-001…014, ADR-046/047/048.

Per [[accounting-test-isolation]]: this file reads AR totals across the shared
test DB (like the pre-existing test_account_balance.py) and must run standalone,
not batched with other tests/accounting/ files.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from dodoo.core.exceptions import DodooError


@pytest_asyncio.fixture
async def bank_journal(env, company_id):
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT id FROM account_journal WHERE type='bank' AND company_id=:cid LIMIT 1"),
            {"cid": company_id},
        )
        return row.scalar_one()


async def _posted_invoice(
    env, company_id, currency_id, journal_sale, revenue_account, partner_id, amount, date=None
):
    """A realistic posted customer invoice: one `product` line only — the AR
    (`payment_term`-display_type) balancing line is auto-derived by
    `_compute_payment_term_lines` at `action_post`, exactly like a real
    invoice-creation flow (mirrors test_early_payment_discount_registration.py)."""
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine

    invoice_date = date or datetime.date.today()
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
        },
    )
    await AccountMoveLine.create(
        env,
        {
            "move_id": move_id,
            "account_id": revenue_account,
            "date": invoice_date,
            "display_type": "product",
            "price_unit": amount,
            "quantity": 1,
            "credit": amount,
        },
    )
    await AccountMove.action_post(env, [move_id])
    return move_id


# --------------------------------------------------------------------------- US1


@pytest.mark.asyncio
async def test_create_customer_with_all_fields(env, company_id, currency_id, payment_term_id):
    from dodoo.addons.account.models.account_partner import write_partner_properties
    from dodoo.addons.base.models.res_partner import ResPartner

    partner_id = await ResPartner.create(
        env,
        {
            "name": "Acme Corp",
            "company_id": company_id,
            "email": "billing@acme.test",
            "phone": "+1-555-0100",
            "street": "1 Main St",
            "city": "Springfield",
            "zip": "00000",
            "vat": "US123456789",
        },
    )
    await write_partner_properties(
        env,
        partner_id,
        {
            "customer_rank": 1,
            "property_payment_term_id": payment_term_id,
            "property_currency_id": currency_id,
        },
    )

    recs = await ResPartner.read(env, [partner_id], ["name", "email", "street", "vat"])
    assert recs[0]["name"] == "Acme Corp"
    assert recs[0]["email"] == "billing@acme.test"
    assert recs[0]["street"] == "1 Main St"
    assert recs[0]["vat"] == "US123456789"

    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT customer_rank, property_payment_term_id, property_currency_id "
                "FROM res_partner WHERE id=:pid"
            ),
            {"pid": partner_id},
        )
        r = row.fetchone()
    assert r.customer_rank == 1
    assert r.property_payment_term_id == payment_term_id
    assert r.property_currency_id == currency_id


@pytest.mark.asyncio
async def test_edit_customer_field_persists(env, customer_id):
    from dodoo.addons.base.models.res_partner import ResPartner

    await ResPartner.write(env, [customer_id], {"street": "2 Second Ave"})
    recs = await ResPartner.read(env, [customer_id], ["street"])
    assert recs[0]["street"] == "2 Second Ave"


@pytest.mark.asyncio
async def test_create_without_name_rejected(env, company_id):
    from dodoo.addons.base.models.res_partner import ResPartner

    with pytest.raises(DodooError):
        await ResPartner.create(env, {"company_id": company_id, "email": "x@example.test"})


@pytest.mark.asyncio
async def test_write_empty_name_rejected(env, customer_id):
    from dodoo.addons.base.models.res_partner import ResPartner

    with pytest.raises(DodooError):
        await ResPartner.write(env, [customer_id], {"name": ""})


@pytest.mark.asyncio
async def test_archive_hides_from_default_search_but_stays_readable(env, customer_id):
    from dodoo.addons.account.models.account_partner import get_ar_ledger
    from dodoo.addons.base.models.res_partner import ResPartner

    await ResPartner.write(env, [customer_id], {"active": False})

    active_ids = await ResPartner.search(env, [["active", "=", True], ["id", "=", customer_id]])
    assert customer_id not in active_ids

    recs = await ResPartner.read(env, [customer_id], ["name", "active"])
    assert recs[0]["active"] is False

    ledger = await get_ar_ledger(env, customer_id)
    assert ledger["balance"] == "0"


@pytest.mark.asyncio
async def test_unlink_blocked_when_referenced_allowed_otherwise(
    env, company_id, currency_id, journal_sale, revenue_account, customer_id
):
    from dodoo.addons.base.models.res_partner import ResPartner

    await _posted_invoice(
        env, company_id, currency_id, journal_sale, revenue_account, customer_id, 100
    )

    with pytest.raises(DodooError):
        await ResPartner.unlink(env, [customer_id])

    # A customer with no financial history can be deleted.
    other_id = await ResPartner.create(env, {"name": "No History Co", "company_id": company_id})
    assert await ResPartner.unlink(env, [other_id]) is True


@pytest.mark.asyncio
async def test_currency_and_payment_term_default_then_override(env, company_id, currency_id):
    from dodoo.addons.account.models.account_partner import write_partner_properties
    from dodoo.addons.base.models.res_partner import ResPartner

    partner_id = await ResPartner.create(env, {"name": "Deferred Defaults Co", "company_id": company_id})

    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT property_currency_id, property_payment_term_id "
                "FROM res_partner WHERE id=:pid"
            ),
            {"pid": partner_id},
        )
        r = row.fetchone()
    assert r.property_currency_id is None
    assert r.property_payment_term_id is None

    await write_partner_properties(env, partner_id, {"property_currency_id": currency_id})
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT property_currency_id FROM res_partner WHERE id=:pid"), {"pid": partner_id}
        )
        assert row.scalar_one() == currency_id


@pytest.mark.asyncio
async def test_duplicate_vat_not_hard_blocked(env, company_id):
    from dodoo.addons.base.models.res_partner import ResPartner

    await ResPartner.create(env, {"name": "First Co", "company_id": company_id, "vat": "DUPVAT001"})
    second_id = await ResPartner.create(
        env, {"name": "Second Co", "company_id": company_id, "vat": "DUPVAT001"}
    )
    assert second_id  # no exception raised — server does not hard-block duplicate VAT


# --------------------------------------------------------------------------- US2


@pytest.mark.asyncio
async def test_search_by_partial_name(env, company_id):
    from dodoo.addons.base.models.res_partner import ResPartner

    await ResPartner.create(env, {"name": "Acme Corp", "company_id": company_id})
    await ResPartner.create(env, {"name": "Acme Studios", "company_id": company_id})
    await ResPartner.create(env, {"name": "Beta LLC", "company_id": company_id})

    ids = await ResPartner.search(env, [["name", "ilike", "%acme%"]])
    recs = await ResPartner.read(env, ids, ["name"])
    names = {r["name"] for r in recs}
    assert names == {"Acme Corp", "Acme Studios"}


@pytest.mark.asyncio
async def test_search_by_exact_vat(env, company_id):
    from dodoo.addons.base.models.res_partner import ResPartner

    target_id = await ResPartner.create(
        env, {"name": "Vat Match Co", "company_id": company_id, "vat": "GB999888777"}
    )
    await ResPartner.create(env, {"name": "Other Co", "company_id": company_id, "vat": "GB111222333"})

    ids = await ResPartner.search(env, [["vat", "=", "GB999888777"]])
    assert ids == [target_id]


@pytest.mark.asyncio
async def test_search_no_matches_returns_empty(env, company_id):
    from dodoo.addons.base.models.res_partner import ResPartner

    ids = await ResPartner.search(env, [["name", "ilike", "%no-such-customer-xyz%"]])
    assert ids == []


# --------------------------------------------------------------------------- US3


@pytest.mark.asyncio
async def test_ar_ledger_balance_and_status_after_partial_payment(
    env, company_id, currency_id, journal_sale, bank_journal, revenue_account, customer_id
):
    from dodoo.addons.account.models.account_partner import get_ar_ledger
    from dodoo.addons.account.models.account_payment import AccountPayment

    move1 = await _posted_invoice(
        env, company_id, currency_id, journal_sale, revenue_account, customer_id, 1000
    )
    await _posted_invoice(
        env, company_id, currency_id, journal_sale, revenue_account, customer_id, 500
    )

    payment_id = await AccountPayment.create(
        env,
        {
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": customer_id,
            "journal_id": bank_journal,
            "currency_id": currency_id,
            "amount": Decimal("250"),
            "date": datetime.date.today(),
            "company_id": company_id,
        },
    )
    await AccountPayment.action_post(env, [payment_id])
    result = await AccountPayment.register_against_invoices(env, payment_id, [move1])
    assert len(result["reconciled"]) == 1

    ledger = await get_ar_ledger(env, customer_id)
    assert Decimal(ledger["balance"]) == Decimal("1250.00")
    statuses = {line["move_id"]: line["status"] for line in ledger["lines"]}
    assert statuses[move1] == "partial"
    types = {line["type"] for line in ledger["lines"]}
    assert types == {"invoice", "payment"}


@pytest.mark.asyncio
async def test_ar_ledger_zero_for_new_customer(env, customer_id):
    from dodoo.addons.account.models.account_partner import get_ar_ledger

    ledger = await get_ar_ledger(env, customer_id)
    assert ledger["balance"] == "0"
    assert ledger["lines"] == []


@pytest.mark.asyncio
async def test_ar_ledger_excludes_cancelled_invoice_from_balance(
    env, company_id, currency_id, journal_sale, revenue_account, customer_id
):
    """FR-012/Edge Cases: a draft invoice cancelled before ever being posted
    (`action_cancel` only accepts `draft` — ADR-038, the only reachable
    `state='cancel'` path for a move in this addon today) never gets a
    `payment_term` line at all, so it must still surface in history with a
    "cancelled" status and contribute nothing to the balance — proving
    get_ar_ledger's separate cancelled-move query (no AR-line join needed)."""
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine
    from dodoo.addons.account.models.account_partner import get_ar_ledger

    # One real, posted invoice — establishes a non-zero baseline balance.
    await _posted_invoice(
        env, company_id, currency_id, journal_sale, revenue_account, customer_id, 300
    )

    # A second invoice that is cancelled while still draft — never posted,
    # so it never receives a payment_term/AR line.
    draft_move_id = await AccountMove.create(
        env,
        {
            "move_type": "out_invoice",
            "journal_id": journal_sale,
            "company_id": company_id,
            "currency_id": currency_id,
            "partner_id": customer_id,
            "date": datetime.date.today(),
        },
    )
    await AccountMoveLine.create(
        env,
        {
            "move_id": draft_move_id,
            "account_id": revenue_account,
            "date": datetime.date.today(),
            "display_type": "product",
            "price_unit": 999,
            "quantity": 1,
            "credit": 999,
        },
    )
    await AccountMove.action_cancel(env, [draft_move_id])

    ledger = await get_ar_ledger(env, customer_id)
    assert Decimal(ledger["balance"]) == Decimal("300.00")  # the cancelled 999 never counted
    statuses = {line["move_id"]: line["status"] for line in ledger["lines"]}
    assert statuses[draft_move_id] == "cancelled"


def test_status_and_balance_pure_unit():
    """T032: no-DB unit test of the pure balance/status helper (Principle II)."""
    from dodoo.addons.account.models.account_partner import _status_and_balance

    lines = [
        {
            "date": datetime.date(2026, 1, 1),
            "type": "invoice",
            "move_id": 1,
            "reference": "INV/0001",
            "amount": "1000",
            "amount_residual": "600",
            "_raw_status": "partial",
        },
        {
            "date": datetime.date(2026, 1, 15),
            "type": "payment",
            "move_id": 2,
            "reference": "PAY/0001",
            "amount": "400",
            "amount_residual": 0,
            "_raw_status": "paid",
        },
        {
            "date": datetime.date(2026, 1, 10),
            "type": "credit_note",
            "move_id": 3,
            "reference": "RINV/0001",
            "amount": "50",
            "amount_residual": "50",
            "_raw_status": "cancelled",
        },
    ]
    balance, out_lines = _status_and_balance(lines)
    # cancelled line's residual (50) must NOT contribute to the balance.
    assert balance == Decimal("600")
    assert [entry["move_id"] for entry in out_lines] == [1, 3, 2]  # sorted by date
    assert out_lines[1]["status"] == "cancelled"
