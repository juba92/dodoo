"""Extends `product`'s `product_category` table with costing/valuation columns (D1/ADR-033) —
the identical `ALTER TABLE` idiom `account/data/account_data.py` uses on `res_partner`. No other
column in this schema carries a DB-level FK constraint (`MigrationRunner._create_table` never
emits `REFERENCES`); these columns follow that same convention — the reference is
business-logic-enforced, not DB-enforced."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text


async def add_valuation_columns(env: Any) -> None:
    async with env.dml_conn() as conn:
        await conn.execute(
            text(
                "ALTER TABLE product_category "
                "ADD COLUMN IF NOT EXISTS costing_method VARCHAR(64) NOT NULL DEFAULT 'standard'"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE product_category "
                "ADD COLUMN IF NOT EXISTS property_stock_valuation_account_id INTEGER"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE product_category "
                "ADD COLUMN IF NOT EXISTS property_stock_input_account_id INTEGER"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE product_category "
                "ADD COLUMN IF NOT EXISTS property_stock_output_account_id INTEGER"
            )
        )
        await conn.commit()
