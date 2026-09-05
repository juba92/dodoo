"""Integration tests for country-driven localization (apply, idempotency, currency guard)."""
from __future__ import annotations

import time

import pytest_asyncio
from sqlalchemy import text

from dodoo.addons.localization.models.res_config_settings import ResConfigSettings
from dodoo.addons.localization.service import apply_country_localization
from dodoo.core.context import set_uid


@pytest_asyncio.fixture(autouse=True)
async def _restore_egypt(env, admin_uid):
    """Every test leaves the company back on Egypt/EGP for the shared session DB."""
    yield
    async with env.dml_conn() as conn:
        egp = await conn.execute(text("SELECT id FROM res_currency WHERE code='EGP'"))
        eg = await conn.execute(text("SELECT id FROM res_country WHERE code='EG'"))
        dom = await conn.execute(
            text("SELECT id FROM account_fiscal_position WHERE name='Domestic' AND company_id=1")
        )
        st = await conn.execute(
            text("SELECT id FROM account_tax WHERE name='VAT 14%' AND company_id=1")
        )
        pt = await conn.execute(
            text("SELECT id FROM account_tax WHERE name='VAT 14% (Purchase)' AND company_id=1")
        )
        await conn.execute(
            text(
                "UPDATE res_company SET country_id=:c, currency_id=:cur, lang='ar', "
                "tax_label='VAT', tax_rounding_method='round_globally', "
                "default_sale_tax_id=:st, default_purchase_tax_id=:pt, "
                "default_fiscal_position_id=:dom WHERE id=1"
            ),
            {
                "c": eg.scalar_one(),
                "cur": egp.scalar_one(),
                "st": st.scalar_one(),
                "pt": pt.scalar_one(),
                "dom": dom.scalar_one(),
            },
        )
        await conn.execute(text("DELETE FROM account_move_line WHERE move_id IN "
                                "(SELECT id FROM account_move WHERE name='L10N-TEST')"))
        await conn.execute(text("DELETE FROM account_move WHERE name='L10N-TEST'"))
        await conn.commit()


async def _counts(env):
    async with env.dml_conn() as conn:
        out = {}
        for label, tbl, where in [
            ("currencies", "res_currency", ""),
            ("taxes", "account_tax", "WHERE company_id=1"),
            ("fps", "account_fiscal_position", "WHERE company_id=1"),
            ("fp_tax", "account_fiscal_position_tax", ""),
        ]:
            r = await conn.execute(text(f"SELECT COUNT(*) FROM {tbl} {where}"))
            out[label] = r.scalar_one()
        return out


async def _make_posted_move(env, currency_code="EUR"):
    async with env.dml_conn() as conn:
        cur = await conn.execute(
            text("SELECT id FROM res_currency WHERE code=:c"), {"c": currency_code}
        )
        cur_id = cur.scalar_one()
        jr = await conn.execute(
            text("SELECT id FROM account_journal WHERE company_id=1 LIMIT 1")
        )
        acc = await conn.execute(
            text("SELECT id FROM account_account WHERE company_id=1 LIMIT 1")
        )
        acc_id = acc.scalar_one()
        mv = await conn.execute(
            text(
                "INSERT INTO account_move (name, move_type, state, date, journal_id, "
                "company_id, currency_id) VALUES ('L10N-TEST','entry','posted', "
                "CURRENT_DATE, :j, 1, :cur) RETURNING id"
            ),
            {"j": jr.scalar_one(), "cur": cur_id},
        )
        mid = mv.scalar_one()
        for debit, credit in ((100, 0), (0, 100)):
            await conn.execute(
                text(
                    "INSERT INTO account_move_line "
                    "(move_id, account_id, date, debit, credit) "
                    "VALUES (:m, :a, CURRENT_DATE, :d, :c)"
                ),
                {"m": mid, "a": acc_id, "d": debit, "c": credit},
            )
        await conn.commit()
        return mid


# ── US3 ──────────────────────────────────────────────────────────────────────
async def test_fresh_install_state_is_egypt(env):
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT (SELECT code FROM res_country WHERE id=c.country_id), "
                "       (SELECT code FROM res_currency WHERE id=c.currency_id), "
                "       tax_label, tax_rounding_method, default_sale_tax_id IS NOT NULL, "
                "       default_purchase_tax_id IS NOT NULL, "
                "       default_fiscal_position_id IS NOT NULL "
                "FROM res_company c WHERE id=1"
            )
        )
        country, currency, label, rounding, ds, dp, dfp = row.one()
    assert (country, currency, label, rounding) == ("EG", "EGP", "VAT", "round_globally")
    assert ds and dp and dfp

    async with env.dml_conn() as conn:
        taxes = await conn.execute(
            text(
                "SELECT name FROM account_tax WHERE company_id=1 AND active=TRUE "
                "AND name LIKE 'VAT%'"
            )
        )
        names = {r[0] for r in taxes}
        fps = await conn.execute(
            text("SELECT name FROM account_fiscal_position WHERE company_id=1")
        )
        fp_names = {r[0] for r in fps}
        generic = await conn.execute(
            text(
                "SELECT active FROM account_tax WHERE company_id=1 AND name='Tax 20.00%'"
            )
        )
        g = generic.fetchone()
    assert names == {"VAT 14%", "VAT 14% (Purchase)", "VAT 0% (Exempt)", "VAT 0% (Export)"}
    assert {"Domestic", "Export"} <= fp_names
    assert g is None or g[0] is False  # generic 20% archived (or never existed here)


async def test_apply_is_idempotent(env):
    before = await _counts(env)
    res = await apply_country_localization(env, 1, "EG")
    assert res["applied"] is True
    assert res["taxes_created"] == 0
    assert res["fiscal_positions_created"] == 0
    assert await _counts(env) == before


async def test_apply_egypt_from_gb_switches_defaults_fast(env):
    # move to neutral GB first
    await apply_country_localization(env, 1, "GB")
    async with env.dml_conn() as conn:
        await conn.execute(text("UPDATE res_company SET currency_id="
                                "(SELECT id FROM res_currency WHERE code='EUR') WHERE id=1"))
        await conn.commit()

    t0 = time.monotonic()
    res = await apply_country_localization(env, 1, "EG", confirm_currency_change=True)
    elapsed = time.monotonic() - t0
    assert res["applied"] is True
    assert elapsed < 3.0
    async with env.dml_conn() as conn:
        cur = await conn.execute(
            text("SELECT code FROM res_currency WHERE id=(SELECT currency_id FROM res_company WHERE id=1)")
        )
    assert cur.scalar_one() == "EGP"


async def test_neutral_country_makes_no_tax_or_currency_changes(env):
    before = await _counts(env)
    async with env.dml_conn() as conn:
        cur_before = await conn.execute(text("SELECT currency_id FROM res_company WHERE id=1"))
        cur_before = cur_before.scalar_one()
    res = await apply_country_localization(env, 1, "GB")
    assert res == {"applied": False, "country": "GB"}
    async with env.dml_conn() as conn:
        cur_after = await conn.execute(text("SELECT currency_id FROM res_company WHERE id=1"))
        assert cur_after.scalar_one() == cur_before
    assert await _counts(env) == before


# ── US4 ──────────────────────────────────────────────────────────────────────
async def test_currency_change_blocked_without_confirm(env, admin_uid):
    # Put the company on GB/EUR and post an entry, then try to move to EG (EGP).
    await apply_country_localization(env, 1, "GB")
    async with env.dml_conn() as conn:
        await conn.execute(text("UPDATE res_company SET currency_id="
                                "(SELECT id FROM res_currency WHERE code='EUR') WHERE id=1"))
        await conn.commit()
    await _make_posted_move(env, "EUR")

    before = await _counts(env)
    set_uid(admin_uid)
    v = await ResConfigSettings.get_values(env)
    res = await ResConfigSettings.set_values(
        env, {"country_code": "EG", "company_write_date": v["company_write_date"]}
    )
    assert res["ok"] is False
    assert res["warning"] == "currency_change_requires_confirmation"
    assert res["detail"]["from"] == "EUR" and res["detail"]["to"] == "EGP"
    assert res["detail"]["posted_lines"] >= 2
    # zero side effects
    assert await _counts(env) == before
    async with env.dml_conn() as conn:
        c = await conn.execute(text("SELECT code FROM res_currency WHERE id="
                                    "(SELECT currency_id FROM res_company WHERE id=1)"))
        assert c.scalar_one() == "EUR"


async def test_currency_change_proceeds_with_confirm_and_preserves_posted(env, admin_uid):
    await apply_country_localization(env, 1, "GB")
    async with env.dml_conn() as conn:
        await conn.execute(text("UPDATE res_company SET currency_id="
                                "(SELECT id FROM res_currency WHERE code='EUR') WHERE id=1"))
        await conn.commit()
    mid = await _make_posted_move(env, "EUR")

    async with env.dml_conn() as conn:
        pre = await conn.execute(
            text("SELECT debit, credit FROM account_move_line WHERE move_id=:m ORDER BY id"),
            {"m": mid},
        )
        pre_rows = [tuple(r) for r in pre]

    set_uid(admin_uid)
    v = await ResConfigSettings.get_values(env)
    res = await ResConfigSettings.set_values(
        env,
        {
            "country_code": "EG",
            "confirm_currency_change": True,
            "company_write_date": v["company_write_date"],
        },
    )
    assert res["ok"] is True
    async with env.dml_conn() as conn:
        post = await conn.execute(
            text("SELECT debit, credit FROM account_move_line WHERE move_id=:m ORDER BY id"),
            {"m": mid},
        )
        post_rows = [tuple(r) for r in post]
        st = await conn.execute(text("SELECT state FROM account_move WHERE id=:m"), {"m": mid})
        cur = await conn.execute(text("SELECT code FROM res_currency WHERE id="
                                      "(SELECT currency_id FROM res_company WHERE id=1)"))
    assert post_rows == pre_rows
    assert st.scalar_one() == "posted"
    assert cur.scalar_one() == "EGP"


async def test_switch_back_reactivates_without_duplicates(env):
    await apply_country_localization(env, 1, "GB")  # away
    async with env.dml_conn() as conn:
        # Egypt taxes remain, just archived-or-active; count rows
        r = await conn.execute(
            text("SELECT COUNT(*) FROM account_tax WHERE company_id=1 AND name LIKE 'VAT%'")
        )
        before = r.scalar_one()
    res = await apply_country_localization(env, 1, "EG", confirm_currency_change=True)
    assert res["taxes_created"] == 0
    async with env.dml_conn() as conn:
        r = await conn.execute(
            text("SELECT COUNT(*) FROM account_tax WHERE company_id=1 AND name LIKE 'VAT%'")
        )
        after = r.scalar_one()
        active = await conn.execute(
            text(
                "SELECT COUNT(*) FROM account_tax "
                "WHERE company_id=1 AND name LIKE 'VAT%' AND active=TRUE"
            )
        )
    assert after == before
    assert active.scalar_one() == 4
