"""Schema migration checks for the localization addon."""
from __future__ import annotations

import pytest
from sqlalchemy import text


async def _columns(env, table):
    async with env.dml_conn() as conn:
        r = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t"
            ),
            {"t": table},
        )
        return {row[0] for row in r}


async def _tables(env):
    async with env.dml_conn() as conn:
        r = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
        )
        return {row[0] for row in r}


@pytest.mark.parametrize("table", ["res_lang", "res_country", "res_country_state"])
async def test_new_tables_exist(env, table):
    assert table in await _tables(env)


async def test_res_company_gained_localization_columns(env):
    cols = await _columns(env, "res_company")
    assert {
        "lang",
        "country_id",
        "tax_label",
        "tax_rounding_method",
        "default_sale_tax_id",
        "default_purchase_tax_id",
        "default_fiscal_position_id",
    } <= cols


async def test_res_users_gained_lang_column(env):
    assert "lang" in await _columns(env, "res_users")


async def test_res_lang_seeded(env):
    async with env.dml_conn() as conn:
        r = await conn.execute(
            text("SELECT code, direction FROM res_lang ORDER BY code")
        )
        rows = {row[0]: row[1] for row in r}
    assert rows == {"ar": "rtl", "en": "ltr"}


async def test_countries_seeded_including_eg_and_gb(env):
    async with env.dml_conn() as conn:
        r = await conn.execute(
            text("SELECT code, currency_code FROM res_country WHERE code IN ('EG', 'GB')")
        )
        rows = {row[0]: row[1] for row in r}
    assert rows == {"EG": "EGP", "GB": "GBP"}
