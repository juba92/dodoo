"""Vendor database: CRUD/archive/delete-guard (US1), search (US2), and the
on-demand AP ledger (US3). FR-001…015, ADR-049/050/051.

Per [[accounting-test-isolation]]: this file reads AP totals across the shared
test DB (like the pre-existing test_customer_database.py) and must run standalone,
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


@pytest_asyncio.fixture
async def journal_purchase(env, company_id):
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT id FROM account_journal WHERE type='purchase' AND company_id=:cid LIMIT 1"
            ),
            {"cid": company_id},
        )
        return row.scalar_one()


@pytest_asyncio.fixture
async def expense_account(env, company_id):
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT id FROM account_account WHERE code='5100' AND company_id=:cid LIMIT 1"),
            {"cid": company_id},
        )
        return row.scalar_one()


async def _posted_bill(
    env, company_id, currency_id, journal_purchase, expense_account, partner_id, amount, date=None
):
    """A realistic posted vendor bill: one `product` line only (debited to an
    expense account, the mirror of `_posted_invoice`'s credited revenue line) —
    the AP (`payment_term`-display_type) balancing line is auto-derived by
    `_compute_payment_term_lines` at `action_post`, exactly like a real
    bill-entry flow."""
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine

    bill_date = date or datetime.date.today()
    move_id = await AccountMove.create(
        env,
        {
            "move_type": "in_invoice",
            "journal_id": journal_purchase,
            "company_id": company_id,
            "currency_id": currency_id,
            "partner_id": partner_id,
            "date": bill_date,
            "invoice_date": bill_date,
        },
    )
    await AccountMoveLine.create(
        env,
        {
            "move_id": move_id,
            "account_id": expense_account,
            "date": bill_date,
            "display_type": "product",
            "price_unit": amount,
            "quantity": 1,
            "debit": amount,
        },
    )
    await AccountMove.action_post(env, [move_id])
    return move_id


# --------------------------------------------------------------------------- US1


@pytest.mark.asyncio
async def test_create_vendor_with_all_fields(env, company_id, currency_id, payment_term_id):
    from dodoo.addons.account.models.account_partner import write_partner_properties
    from dodoo.addons.base.models.res_partner import ResPartner

    partner_id = await ResPartner.create(
        env,
        {
            "name": "Global Supply Co",
            "company_id": company_id,
            "email": "ap@globalsupply.test",
            "phone": "+1-555-0200",
            "street": "9 Industrial Way",
            "city": "Riverside",
            "zip": "00001",
            "vat": "US987654321",
        },
    )
    await write_partner_properties(
        env,
        partner_id,
        {
            "supplier_rank": 1,
            "property_supplier_payment_term_id": payment_term_id,
            "property_currency_id": currency_id,
        },
    )

    recs = await ResPartner.read(env, [partner_id], ["name", "email", "street", "vat"])
    assert recs[0]["name"] == "Global Supply Co"
    assert recs[0]["email"] == "ap@globalsupply.test"
    assert recs[0]["street"] == "9 Industrial Way"
    assert recs[0]["vat"] == "US987654321"

    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT supplier_rank, property_supplier_payment_term_id, property_currency_id "
                "FROM res_partner WHERE id=:pid"
            ),
            {"pid": partner_id},
        )
        r = row.fetchone()
    assert r.supplier_rank == 1
    assert r.property_supplier_payment_term_id == payment_term_id
    assert r.property_currency_id == currency_id


@pytest.mark.asyncio
async def test_edit_vendor_field_persists(env, vendor_id):
    from dodoo.addons.base.models.res_partner import ResPartner

    await ResPartner.write(env, [vendor_id], {"street": "10 Industrial Way"})
    recs = await ResPartner.read(env, [vendor_id], ["street"])
    assert recs[0]["street"] == "10 Industrial Way"


@pytest.mark.asyncio
async def test_create_without_name_rejected(env, company_id):
    from dodoo.addons.base.models.res_partner import ResPartner

    with pytest.raises(DodooError):
        await ResPartner.create(env, {"company_id": company_id, "email": "x@example.test"})


@pytest.mark.asyncio
async def test_write_empty_name_rejected(env, vendor_id):
    from dodoo.addons.base.models.res_partner import ResPartner

    with pytest.raises(DodooError):
        await ResPartner.write(env, [vendor_id], {"name": ""})


@pytest.mark.asyncio
async def test_archive_hides_from_default_search_but_stays_readable(env, vendor_id):
    from dodoo.addons.account.models.account_partner import get_ap_ledger
    from dodoo.addons.base.models.res_partner import ResPartner

    await ResPartner.write(env, [vendor_id], {"active": False})

    active_ids = await ResPartner.search(env, [["active", "=", True], ["id", "=", vendor_id]])
    assert vendor_id not in active_ids

    recs = await ResPartner.read(env, [vendor_id], ["name", "active"])
    assert recs[0]["active"] is False

    ledger = await get_ap_ledger(env, vendor_id)
    assert ledger["balance"] == "0"


@pytest.mark.asyncio
async def test_unlink_blocked_when_referenced_allowed_otherwise(
    env, company_id, currency_id, journal_purchase, expense_account, vendor_id
):
    from dodoo.addons.base.models.res_partner import ResPartner

    await _posted_bill(
        env, company_id, currency_id, journal_purchase, expense_account, vendor_id, 100
    )

    with pytest.raises(DodooError):
        await ResPartner.unlink(env, [vendor_id])

    # A vendor with no financial history can be deleted.
    other_id = await ResPartner.create(env, {"name": "No History Supplier", "company_id": company_id})
    assert await ResPartner.unlink(env, [other_id]) is True


@pytest.mark.asyncio
async def test_currency_and_payment_term_default_then_override(env, company_id, currency_id):
    from dodoo.addons.account.models.account_partner import write_partner_properties
    from dodoo.addons.base.models.res_partner import ResPartner

    partner_id = await ResPartner.create(
        env, {"name": "Deferred Defaults Supplier", "company_id": company_id}
    )

    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT property_currency_id, property_supplier_payment_term_id "
                "FROM res_partner WHERE id=:pid"
            ),
            {"pid": partner_id},
        )
        r = row.fetchone()
    assert r.property_currency_id is None
    assert r.property_supplier_payment_term_id is None

    await write_partner_properties(env, partner_id, {"property_currency_id": currency_id})
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT property_currency_id FROM res_partner WHERE id=:pid"), {"pid": partner_id}
        )
        assert row.scalar_one() == currency_id


@pytest.mark.asyncio
async def test_duplicate_vat_not_hard_blocked(env, company_id):
    from dodoo.addons.base.models.res_partner import ResPartner

    await ResPartner.create(
        env, {"name": "First Supplier", "company_id": company_id, "vat": "DUPVAT002"}
    )
    second_id = await ResPartner.create(
        env, {"name": "Second Supplier", "company_id": company_id, "vat": "DUPVAT002"}
    )
    assert second_id  # no exception raised — server does not hard-block duplicate VAT


@pytest.mark.asyncio
async def test_existing_customer_promoted_to_also_be_vendor(
    env, company_id, currency_id, payment_term_id
):
    """FR-014/015, Edge Cases: a partner already known as a customer can be
    promoted to also be a vendor on the same row, with independent ledgers.

    Built inline via `ResPartner.create` + `write_partner_properties` (not the
    `customer_id` fixture) — that fixture passes `customer_rank`/
    `property_payment_term_id`/`property_currency_id` directly into `create`'s
    `vals`, which `BaseModel.create` silently drops since none of those three
    are declared `Field`s on `ResPartner`; confirmed by reading
    `dodoo/core/models.py::BaseModel.create` directly."""
    from dodoo.addons.account.models.account_partner import (
        get_ap_ledger,
        get_ar_ledger,
        write_partner_properties,
    )
    from dodoo.addons.base.models.res_partner import ResPartner

    partner_id = await ResPartner.create(
        env, {"name": "Dual Role Co", "company_id": company_id}
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

    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT customer_rank, supplier_rank FROM res_partner WHERE id=:pid"),
            {"pid": partner_id},
        )
        r = row.fetchone()
    assert r.customer_rank == 1
    assert r.supplier_rank == 0

    await write_partner_properties(
        env,
        partner_id,
        {"supplier_rank": 1, "property_supplier_payment_term_id": payment_term_id},
    )

    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT customer_rank, supplier_rank FROM res_partner WHERE id=:pid"),
            {"pid": partner_id},
        )
        r = row.fetchone()
    assert r.customer_rank == 1
    assert r.supplier_rank == 1

    # Independent, correctly-scoped ledgers on the same partner id.
    ar_ledger = await get_ar_ledger(env, partner_id)
    ap_ledger = await get_ap_ledger(env, partner_id)
    assert ar_ledger["balance"] == "0"
    assert ap_ledger["balance"] == "0"


# --------------------------------------------------------------------------- US2


@pytest.mark.asyncio
async def test_search_by_partial_name(env, company_id):
    from dodoo.addons.base.models.res_partner import ResPartner

    await ResPartner.create(env, {"name": "Global Supply Co", "company_id": company_id})
    await ResPartner.create(env, {"name": "Global Freight", "company_id": company_id})
    await ResPartner.create(env, {"name": "Beta Materials", "company_id": company_id})

    ids = await ResPartner.search(env, [["name", "ilike", "%global%"]])
    recs = await ResPartner.read(env, ids, ["name"])
    names = {r["name"] for r in recs}
    assert names == {"Global Supply Co", "Global Freight"}


@pytest.mark.asyncio
async def test_search_by_exact_vat(env, company_id):
    from dodoo.addons.base.models.res_partner import ResPartner

    target_id = await ResPartner.create(
        env, {"name": "Vat Match Supplier", "company_id": company_id, "vat": "GB444555666"}
    )
    await ResPartner.create(
        env, {"name": "Other Supplier", "company_id": company_id, "vat": "GB777888999"}
    )

    ids = await ResPartner.search(env, [["vat", "=", "GB444555666"]])
    assert ids == [target_id]


@pytest.mark.asyncio
async def test_search_no_matches_returns_empty(env, company_id):
    from dodoo.addons.base.models.res_partner import ResPartner

    ids = await ResPartner.search(env, [["name", "ilike", "%no-such-vendor-xyz%"]])
    assert ids == []


# --------------------------------------------------------------------------- US3


@pytest.mark.asyncio
async def test_ap_ledger_balance_and_status_after_partial_payment(
    env, company_id, currency_id, journal_purchase, bank_journal, expense_account, vendor_id
):
    from dodoo.addons.account.models.account_partner import get_ap_ledger
    from dodoo.addons.account.models.account_payment import AccountPayment

    move1 = await _posted_bill(
        env, company_id, currency_id, journal_purchase, expense_account, vendor_id, 1000
    )
    await _posted_bill(
        env, company_id, currency_id, journal_purchase, expense_account, vendor_id, 500
    )

    payment_id = await AccountPayment.create(
        env,
        {
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": vendor_id,
            "journal_id": bank_journal,
            "currency_id": currency_id,
            "amount": Decimal("125"),
            "date": datetime.date.today(),
            "company_id": company_id,
        },
    )
    await AccountPayment.action_post(env, [payment_id])
    result = await AccountPayment.register_against_invoices(env, payment_id, [move1])
    assert len(result["reconciled"]) == 1

    ledger = await get_ap_ledger(env, vendor_id)
    assert Decimal(ledger["balance"]) == Decimal("1375.00")
    statuses = {line["move_id"]: line["status"] for line in ledger["lines"]}
    assert statuses[move1] == "partial"
    types = {line["type"] for line in ledger["lines"]}
    assert types == {"bill", "payment"}


@pytest.mark.asyncio
async def test_ap_ledger_zero_for_new_vendor(env, vendor_id):
    from dodoo.addons.account.models.account_partner import get_ap_ledger

    ledger = await get_ap_ledger(env, vendor_id)
    assert ledger["balance"] == "0"
    assert ledger["lines"] == []


@pytest.mark.asyncio
async def test_ap_ledger_excludes_cancelled_bill_from_balance(
    env, company_id, currency_id, journal_purchase, expense_account, vendor_id
):
    """FR-012/Edge Cases: a draft bill cancelled before ever being posted
    (`action_cancel` only accepts `draft` — ADR-038) never gets a
    `payment_term` line at all, so it must still surface in history with a
    "cancelled" status and contribute nothing to the balance."""
    from dodoo.addons.account.models.account_move import AccountMove
    from dodoo.addons.account.models.account_move_line import AccountMoveLine
    from dodoo.addons.account.models.account_partner import get_ap_ledger

    # One real, posted bill — establishes a non-zero baseline balance.
    await _posted_bill(
        env, company_id, currency_id, journal_purchase, expense_account, vendor_id, 300
    )

    # A second bill that is cancelled while still draft — never posted, so it
    # never receives a payment_term/AP line.
    draft_move_id = await AccountMove.create(
        env,
        {
            "move_type": "in_invoice",
            "journal_id": journal_purchase,
            "company_id": company_id,
            "currency_id": currency_id,
            "partner_id": vendor_id,
            "date": datetime.date.today(),
        },
    )
    await AccountMoveLine.create(
        env,
        {
            "move_id": draft_move_id,
            "account_id": expense_account,
            "date": datetime.date.today(),
            "display_type": "product",
            "price_unit": 999,
            "quantity": 1,
            "debit": 999,
        },
    )
    await AccountMove.action_cancel(env, [draft_move_id])

    ledger = await get_ap_ledger(env, vendor_id)
    assert Decimal(ledger["balance"]) == Decimal("300.00")  # the cancelled 999 never counted
    statuses = {line["move_id"]: line["status"] for line in ledger["lines"]}
    assert statuses[draft_move_id] == "cancelled"


def test_status_and_balance_reused_for_ap_shaped_input():
    """T030: confirms the AR-side's pure `_status_and_balance` helper (already
    unit-tested in test_customer_database.py) behaves identically when fed
    AP-labeled ("bill") `type` values — proving it's genuinely type-agnostic
    and safe to reuse unmodified for get_ap_ledger (research.md D5)."""
    from dodoo.addons.account.models.account_partner import _status_and_balance

    lines = [
        {
            "date": datetime.date(2026, 1, 1),
            "type": "bill",
            "move_id": 1,
            "reference": "BILL/0001",
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
            "reference": "RBILL/0001",
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
