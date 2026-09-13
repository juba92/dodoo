"""Reconciliation write-off posting and currency-aware partial reconcile
(FR-020/022, ADR-042)."""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text


@pytest_asyncio.fixture
async def writeoff_account(env, company_id):
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT id FROM account_account WHERE code='5100' AND company_id=:cid"),
            {"cid": company_id},
        )
        return row.scalar_one()


@pytest_asyncio.fixture
async def usd_currency_id(env):
    async with env.dml_conn() as conn:
        row = await conn.execute(text("SELECT id FROM res_currency WHERE code='USD'"))
        r = row.fetchone()
        if r:
            return r[0]
    from dodoo.addons.base.models.res_currency import ResCurrency

    return await ResCurrency.create(
        env, {"code": "USD", "name": "US Dollar", "symbol": "$", "rounding": 2}
    )


async def _post_ar_line_move(
    env, *, journal_id, company_id, partner_id, amount, header_currency_id,
    line_currency_id=None, amount_currency=None
):
    """Post a two-line ``entry`` move: one AR (payment_term) line for
    ``amount`` (positive = debit/receivable, negative = credit) plus a
    balancing line, returning the AR line's id.

    ``header_currency_id`` is the move's own currency — always the company's
    own currency here, so `action_post`'s FX-conversion-at-posting step
    (FR-024, keyed off the *header* currency) never fires and never needs a
    ``res_currency_rate`` row. ``line_currency_id``/``amount_currency`` are
    set directly on the AR line only, independent of the header, to exercise
    `reconcile_lines`'s own currency-aware residual logic (FR-022) in
    isolation — a low-level raw-SQL construction, not the normal invoice flow.
    """
    from dodoo.addons.account.models.account_move import AccountMove

    async with env.dml_conn() as conn:
        ar_row = await conn.execute(
            text(
                "SELECT id FROM account_account WHERE account_type='asset_receivable' "
                "AND company_id=:cid"
            ),
            {"cid": company_id},
        )
        ar_account_id = ar_row.scalar_one()
        bank_row = await conn.execute(
            text("SELECT id FROM account_account WHERE code='1020' AND company_id=:cid"),
            {"cid": company_id},
        )
        bank_account_id = bank_row.scalar_one()

    move_id = await AccountMove.create(
        env,
        {
            "move_type": "entry",
            "journal_id": journal_id,
            "company_id": company_id,
            "currency_id": header_currency_id,
            "date": datetime.date(2026, 1, 1),
        },
    )
    magnitude = abs(amount)
    ar_debit = magnitude if amount >= 0 else Decimal("0")
    ar_credit = Decimal("0") if amount >= 0 else magnitude
    other_debit = Decimal("0") if amount >= 0 else magnitude
    other_credit = magnitude if amount >= 0 else Decimal("0")

    async with env.dml_conn() as conn:
        ar_line_row = await conn.execute(
            text(
                "INSERT INTO account_move_line "
                "(move_id, account_id, partner_id, date, display_type, debit, credit, "
                "balance, amount_residual, currency_id, amount_currency, "
                "create_date, write_date) "
                "VALUES (:mid, :acct, :pid, :dt, 'payment_term', :d, :c, :bal, :bal, "
                ":cur, :ac, now(), now()) RETURNING id"
            ),
            {
                "mid": move_id,
                "acct": ar_account_id,
                "pid": partner_id,
                "dt": datetime.date(2026, 1, 1),
                "d": str(ar_debit),
                "c": str(ar_credit),
                "bal": str(ar_debit - ar_credit),
                "cur": line_currency_id,
                "ac": str(amount_currency) if amount_currency is not None else "0",
            },
        )
        ar_line_id = ar_line_row.scalar_one()
        await conn.execute(
            text(
                "INSERT INTO account_move_line "
                "(move_id, account_id, date, display_type, debit, credit, balance, "
                "create_date, write_date) "
                "VALUES (:mid, :acct, :dt, 'product', :d, :c, :bal, now(), now())"
            ),
            {
                "mid": move_id,
                "acct": bank_account_id,
                "dt": datetime.date(2026, 1, 1),
                "d": str(other_debit),
                "c": str(other_credit),
                "bal": str(other_debit - other_credit),
            },
        )
        await conn.commit()

    await AccountMove.action_post(env, [move_id])
    return ar_line_id


@pytest.mark.asyncio
async def test_writeoff_closes_residual_gap(
    env, company_id, currency_id, journal_sale, partner_id, writeoff_account
):
    """FR-020: a short payment (98 against a 100 receivable) reconciled with a
    write-off closes both lines fully and posts the 2.00 gap."""
    from dodoo.addons.account.models.account_reconcile import AccountPartialReconcile

    debit_line_id = await _post_ar_line_move(
        env, journal_id=journal_sale, company_id=company_id, partner_id=partner_id,
        amount=Decimal("100.00"), header_currency_id=currency_id,
    )
    credit_line_id = await _post_ar_line_move(
        env, journal_id=journal_sale, company_id=company_id, partner_id=partner_id,
        amount=Decimal("-98.00"), header_currency_id=currency_id,
    )

    result = await AccountPartialReconcile.reconcile_lines(
        env, debit_line_id, credit_line_id, writeoff_account_id=writeoff_account
    )

    assert result["writeoff_move_id"] is not None
    assert result["full_reconcile_id"] is not None

    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT amount_residual, reconciled FROM account_move_line "
                "WHERE id IN (:did, :cid)"
            ),
            {"did": debit_line_id, "cid": credit_line_id},
        )
        residuals = list(row)
    for residual, reconciled in residuals:
        assert abs(Decimal(str(residual))) < Decimal("0.01")
        assert reconciled is True

    async with env.dml_conn() as conn:
        writeoff_row = await conn.execute(
            text(
                "SELECT debit, credit FROM account_move_line "
                "WHERE move_id=:mid AND account_id=:acct"
            ),
            {"mid": result["writeoff_move_id"], "acct": writeoff_account},
        )
        writeoff_line = writeoff_row.fetchone()
    assert writeoff_line is not None
    assert Decimal(str(writeoff_line[0])) - Decimal(str(writeoff_line[1])) == Decimal("2.00")


@pytest.mark.asyncio
async def test_partial_reconcile_populates_amount_currency(
    env, company_id, currency_id, journal_sale, partner_id, usd_currency_id
):
    """FR-022: a partial (not full) reconciliation between two same-foreign-
    currency lines records each side's proportional ``*_amount_currency``."""
    from dodoo.addons.account.models.account_reconcile import AccountPartialReconcile

    debit_line_id = await _post_ar_line_move(
        env, journal_id=journal_sale, company_id=company_id, partner_id=partner_id,
        amount=Decimal("200.00"), header_currency_id=currency_id,
        line_currency_id=usd_currency_id, amount_currency=Decimal("200.00"),
    )
    credit_line_id = await _post_ar_line_move(
        env, journal_id=journal_sale, company_id=company_id, partner_id=partner_id,
        amount=Decimal("-200.00"), header_currency_id=currency_id,
        line_currency_id=usd_currency_id, amount_currency=Decimal("-200.00"),
    )

    result = await AccountPartialReconcile.reconcile_lines(
        env, debit_line_id, credit_line_id, amount=Decimal("50.00")
    )

    assert result["full_reconcile_id"] is None

    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT debit_amount_currency, credit_amount_currency "
                "FROM account_partial_reconcile WHERE id=:pid"
            ),
            {"pid": result["partial_id"]},
        )
        dca, cca = row.fetchone()

    assert Decimal(str(dca)) == Decimal("50.00")
    assert Decimal(str(cca)) == Decimal("-50.00")

    async with env.dml_conn() as conn:
        row = await conn.execute(
            text("SELECT id, amount_residual FROM account_move_line WHERE id IN (:did, :cid)"),
            {"did": debit_line_id, "cid": credit_line_id},
        )
        residual_by_id = {r[0]: Decimal(str(r[1])) for r in row}
    assert residual_by_id[debit_line_id] == Decimal("150.00")
    assert residual_by_id[credit_line_id] == Decimal("-150.00")
