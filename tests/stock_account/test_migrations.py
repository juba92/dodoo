"""Every stock_account table/extension-column exists after install (data-model.md)."""

from __future__ import annotations

from sqlalchemy import text


async def test_valuation_layer_table_exists(env):
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'stock_valuation_layer'"
            )
        )
        assert row.fetchone() is not None


async def test_category_extension_columns_exist(env):
    async with env.dml_conn() as conn:
        for col in [
            "costing_method",
            "property_stock_valuation_account_id",
            "property_stock_input_account_id",
            "property_stock_output_account_id",
        ]:
            row = await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'product_category' AND column_name = :c"
                ),
                {"c": col},
            )
            assert row.fetchone() is not None, f"missing column product_category.{col}"


async def test_product_extension_column_exists(env):
    async with env.dml_conn() as conn:
        row = await conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'product_product' AND column_name = 'stock_avg_cost'"
            )
        )
        assert row.fetchone() is not None
