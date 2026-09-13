"""Every product table exists after install (data-model.md)."""

from __future__ import annotations

from sqlalchemy import text

_TABLES = [
    "product_category",
    "uom_category",
    "uom_uom",
    "product_template",
    "product_attribute",
    "product_attribute_value",
    "product_template_attribute_line",
    "product_product",
]


async def test_all_tables_exist(env):
    async with env.dml_conn() as conn:
        for table in _TABLES:
            row = await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = :t"
                ),
                {"t": table},
            )
            assert row.fetchone() is not None, f"missing table {table}"
